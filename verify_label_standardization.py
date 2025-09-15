#!/usr/bin/env python3
# =============================================================================
# GitHub Label Color Standardization Verification Script
# GitHub 标签颜色标准化验证脚本：支持配置化适配不同项目，验证标签体系标准化流程
# 依赖：requests, python-dotenv（安装：pip install requests python-dotenv）
# =============================================================================

import sys
import os
import requests
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# =============================================================================
# 配置区域（根据实际项目需求修改）
# =============================================================================

CONFIG = {
    # 目标仓库信息
    "target_repo": "label-project",  # 实际项目仓库名
    
    # 功能分支配置
    "feature_branch": {
        "name": "main",  # 标签标准化功能分支名
        "doc_file": "docs/label-color-standardization.md"  # 标签标准文档路径
    },
    
    # 标签文档解析配置
    "doc_parsing": {
        "table_header": "| Label Name | Color Hex | Category |",  # 文档中标签表格头部
        "min_label_count": 22  # 文档至少需包含的标签数量
    },
    
    # Issue验证配置
    "issue_requirements": {
        "title_keywords": ["Document label color standard", "Label organization"],  # Issue标题关键词
        "body_keywords": ["label color documentation", "standardize label colors", "label category definition"],  # Issue内容关键词
        "required_sections": ["## Background", "## Required Label List", "## Color Standard Rules"],  # Issue必需章节
        "initial_labels": ["documentation", "enhancement"]  # Issue初始必需标签
    },
    
    # PR验证配置
    "pr_requirements": {
        "title_keywords": ["Add label color standard doc", "Label standardization"],  # PR标题关键词
        "body_keywords": ["label color doc", "reference issue #", "label list verification"],  # PR内容关键词
        "required_sections": ["## Summary", "## Doc Content", "## Issue Reference"],  # PR必需章节
        "min_labels_count": 5,  # PR至少需包含的标签数量
        "issue_reference_pattern": "Fixes #{issue_number}"  # PR关联Issue的格式
    },
    
    # 预期标签配置（项目实际使用的22个标签）
    "expected_labels": [
        "bug", "enhancement", "documentation", "feature", "bug-critical", 
        "bug-major", "bug-minor", "task", "question", "help-wanted",
        "good-first-issue", "priority-high", "priority-medium", "priority-low",
        "status-in-progress", "status-review", "status-done", "status-blocked",
        "component-frontend", "component-backend", "component-db", "wontfix"
    ],
    
    # Issue评论验证配置
    "comment_requirements": {
        "keywords": ["label documentation completed", "total labels verified", "color standard applied"],  # 评论必需关键词
        "pr_reference_flag": "PR #{pr_number}",  # 评论关联PR的格式
        "content_flags": ["22 labels", "color hex checked", "category mapped"]  # 评论必需内容标识
    }
}

# =============================================================================
# 通用工具函数（无需修改，直接复用）
# =============================================================================

def _get_github_api(
    endpoint: str, headers: Dict[str, str], org: str, repo: str
) -> Tuple[bool, Optional[Dict]]:
    """通用GitHub API请求函数：发起GET请求，返回（请求成功状态，响应数据）"""
    url = f"https://api.github.com/repos/{org}/{repo}/{endpoint}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return True, response.json()
        elif response.status_code == 404:
            print(f"[API提示] {endpoint} 资源未找到（404）", file=sys.stderr)
            return False, None
        else:
            print(f"[API错误] {endpoint} 状态码：{response.status_code}", file=sys.stderr)
            return False, None
    except Exception as e:
        print(f"[API异常] 调用 {endpoint} 失败：{str(e)}", file=sys.stderr)
        return False, None

def _check_branch_exists(
    branch_name: str, headers: Dict[str, str], org: str, repo: str
) -> bool:
    """验证目标分支是否存在"""
    success, _ = _get_github_api(f"{branch_name}", headers, org, repo)
    return success

def _get_file_content(
    branch: str, file_path: str, headers: Dict[str, str], org: str, repo: str
) -> Optional[str]:
    """从指定分支获取文件内容（Base64解码）"""
    import base64
    success, result = _get_github_api(
        f"contents/{file_path}?ref={branch}", headers, org, repo
    )
    if not success or not result:
        return None
    if result.get("content"):
        try:
            return base64.b64decode(result["content"]).decode("utf-8")
        except Exception as e:
            print(f"[文件解码错误] {file_path}：{str(e)}", file=sys.stderr)
            return None
    return None

def _parse_label_table(content: str, table_header: str) -> List[str]:
    """通用标签表格解析：从Markdown内容中提取标签名（支持自定义表格头部）"""
    documented_labels = []
    lines = content.split("\n")
    in_table = False
    for line in lines:
        # 识别表格头部（支持配置化）
        if table_header in line:
            in_table = True
            continue
        # 跳过表格分隔线（如"|--|--|--|"）
        if in_table and line.startswith("|---"):
            continue
        # 解析表格行（按"| 内容 | 内容 | 内容 |"格式）
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:  # 匹配"空|标签名|颜色|分类|空"格式
                label_name = parts[1]
                if label_name:
                    documented_labels.append(label_name)
        # 识别表格结束（遇到非表格行）
        if in_table and line and not line.startswith("|"):
            break
    return documented_labels

def _find_issue_by_keywords(
    title_keywords: List[str], headers: Dict[str, str], org: str, repo: str
) -> Optional[Dict]:
    """按标题关键词查找Issue（支持匹配多个关键词，忽略大小写）"""
    for state in ["open", "closed"]:
        success, issues = _get_github_api(
            f"issues?state={state}&per_page=30", headers, org, repo
        )
        if success and issues:
            for issue in issues:
                # 跳过PR（仅匹配纯Issue）
                if "pull_request" in issue:
                    continue
                title = issue.get("title", "").lower()
                if all(kw.lower() in title for kw in title_keywords):
                    return issue
    return None

def _find_pr_by_keywords(
    title_keywords: List[str], headers: Dict[str, str], org: str, repo: str
) -> Optional[Dict]:
    """按标题关键词查找PR（支持匹配多个关键词，忽略大小写）"""
    for state in ["open", "closed"]:
        success, prs = _get_github_api(
            f"pulls?state={state}&per_page=30", headers, org, repo
        )
        if success and prs:
            for pr in prs:
                title = pr.get("title", "").lower()
                if all(kw.lower() in title for kw in title_keywords):
                    return pr
    return None

def _get_issue_comments(
    issue_number: int, headers: Dict[str, str], org: str, repo: str
) -> List[Dict]:
    """获取指定Issue的所有评论"""
    success, comments = _get_github_api(
        f"issues/{issue_number}/comments", headers, org, repo
    )
    return comments if (success and comments) else []

# =============================================================================
# 核心验证流程
# =============================================================================

def verify_label_standardization() -> bool:
    """标签颜色标准化验证主流程：按配置完成全链路校验"""
    
    # --------------------------
    # 步骤1：加载环境变量（基础配置）
    # --------------------------
    load_dotenv(".env")  # 环境变量文件（存放GitHub令牌和组织名）
    github_token = os.environ.get("GITHUB_TOKEN")  # GitHub访问令牌环境变量名
    github_org = os.environ.get("GITHUB_ORG")  # GitHub组织/用户名环境变量名
    
    # 校验环境变量
    if not github_token:
        print(f"[环境错误] 未配置 GITHUB_TOKEN（需在 .env 中设置）", file=sys.stderr)
        return False
    if not github_org:
        print(f"[环境错误] 未配置 GITHUB_ORG（需在 .env 中设置）", file=sys.stderr)
        return False
    
    # 构建API请求头
    headers = {
        "Authorization": f"token {github_token}",  # GitHub API授权格式
        "Accept": "application/vnd.github.v3+json"  # GitHub API v3版本
    }
    
    print("=" * 60)
    print("开始执行标签颜色标准化验证（GitHub场景）")
    print(f"目标仓库：{github_org}/{CONFIG['target_repo']}")
    print("=" * 60)
    
    # --------------------------
    # 步骤2：验证功能分支存在性
    # --------------------------
    print(f"\n1/8 验证功能分支：{CONFIG['feature_branch']['name']}...")
    if not _check_branch_exists(
        CONFIG["feature_branch"]["name"], headers, github_org, CONFIG["target_repo"]
    ):
        print(f"[错误] 功能分支 {CONFIG['feature_branch']['name']} 未找到", file=sys.stderr)
        return False
    print(f"✓ 功能分支 {CONFIG['feature_branch']['name']} 存在")
    
    # --------------------------
    # 步骤3：验证标签文档完整性
    # --------------------------
    print(f"\n2/8 验证标签文档：{CONFIG['feature_branch']['doc_file']}...")
    doc_content = _get_file_content(
        branch=CONFIG["feature_branch"]["name"],
        file_path=CONFIG["feature_branch"]["doc_file"],
        headers=headers,
        org=github_org,
        repo=CONFIG["target_repo"]
    )
    if not doc_content:
        print(f"[错误] 标签文档 {CONFIG['feature_branch']['doc_file']} 未找到", file=sys.stderr)
        return False
    
    # 解析文档中的标签列表
    documented_labels = _parse_label_table(
        content=doc_content,
        table_header=CONFIG["doc_parsing"]["table_header"]
    )
    if len(documented_labels) < CONFIG["doc_parsing"]["min_label_count"]:
        print(f"[错误] 文档标签数量不足：实际 {len(documented_labels)} 个，需至少 {CONFIG['doc_parsing']['min_label_count']} 个", file=sys.stderr)
        return False
    print(f"✓ 标签文档存在，共包含 {len(documented_labels)} 个标签")
    
    # --------------------------
    # 步骤4：验证Issue创建与合规性
    # --------------------------
    print(f"\n3/8 验证Issue（关键词：{CONFIG['issue_requirements']['title_keywords']}）...")
    issue = _find_issue_by_keywords(
        title_keywords=CONFIG["issue_requirements"]["title_keywords"],
        headers=headers,
        org=github_org,
        repo=CONFIG["target_repo"]
    )
    if not issue:
        print("[错误] 未找到符合关键词的Issue", file=sys.stderr)
        return False
    
    issue_number = issue["number"]
    issue_body = issue.get("body", "")
    issue_labels = [label["name"] for label in issue.get("labels", [])]
    
    # 校验Issue必需章节
    missing_issue_sections = [
        sec for sec in CONFIG["issue_requirements"]["required_sections"] 
        if sec not in issue_body
    ]
    if missing_issue_sections:
        print(f"[错误] Issue缺失必需章节：{', '.join(missing_issue_sections)}", file=sys.stderr)
        return False
    
    # 校验Issue必需关键词
    missing_issue_keywords = [
        kw for kw in CONFIG["issue_requirements"]["body_keywords"] 
        if kw.lower() not in issue_body.lower()
    ]
    if missing_issue_keywords:
        print(f"[错误] Issue缺失必需关键词：{', '.join(missing_issue_keywords)}", file=sys.stderr)
        return False
    
    # 校验Issue初始标签
    missing_issue_labels = [
        lbl for lbl in CONFIG["issue_requirements"]["initial_labels"] 
        if lbl not in issue_labels
    ]
    if missing_issue_labels:
        print(f"[错误] Issue缺失初始必需标签：{', '.join(missing_issue_labels)}", file=sys.stderr)
        return False
    
    print(f"✓ Issue #{issue_number} 合规（标题：{issue['title']}）")
    
    # --------------------------
    # 步骤5：验证PR创建与合规性
    # --------------------------
    print(f"\n4/8 验证PR（关键词：{CONFIG['pr_requirements']['title_keywords']}）...")
    pr = _find_pr_by_keywords(
        title_keywords=CONFIG["pr_requirements"]["title_keywords"],
        headers=headers,
        org=github_org,
        repo=CONFIG["target_repo"]
    )
    if not pr:
        print("[错误] 未找到符合关键词的PR", file=sys.stderr)
        return False
    
    pr_number = pr["number"]
    pr_body = pr.get("body", "")
    pr_labels = pr.get("labels", [])
    
    # 校验PR关联Issue格式
    expected_issue_ref = CONFIG["pr_requirements"]["issue_reference_pattern"].format(issue_number=issue_number)
    if expected_issue_ref.lower() not in pr_body.lower():
        print(f"[错误] PR未按格式关联Issue：需包含「{expected_issue_ref}」", file=sys.stderr)
        return False
    
    # 校验PR必需章节
    missing_pr_sections = [
        sec for sec in CONFIG["pr_requirements"]["required_sections"] 
        if sec not in pr_body
    ]
    if missing_pr_sections:
        print(f"[错误] PR缺失必需章节：{', '.join(missing_pr_sections)}", file=sys.stderr)
        return False
    
    # 校验PR必需关键词
    missing_pr_keywords = [
        kw for kw in CONFIG["pr_requirements"]["body_keywords"] 
        if kw.lower() not in pr_body.lower()
    ]
    if missing_pr_keywords:
        print(f"[错误] PR缺失必需关键词：{', '.join(missing_pr_keywords)}", file=sys.stderr)
        return False
    
    # 校验PR标签数量
    if len(pr_labels) < CONFIG["pr_requirements"]["min_labels_count"]:
        print(f"[错误] PR标签数量不足：实际 {len(pr_labels)} 个，需至少 {CONFIG['pr_requirements']['min_labels_count']} 个", file=sys.stderr)
        return False
    
    print(f"✓ PR #{pr_number} 合规（标题：{pr['title']}）")
    
    # --------------------------
    # 步骤6：验证Issue标签完整性
    # --------------------------
    print(f"\n5/8 验证Issue标签完整性（共需 {len(CONFIG['expected_labels'])} 个标签）...")
    missing_issue_all_labels = [
        lbl for lbl in CONFIG["expected_labels"] 
        if lbl not in issue_labels
    ]
    if missing_issue_all_labels:
        print(f"[错误] Issue缺失 {len(missing_issue_all_labels)} 个预期标签：{missing_issue_all_labels[:5]}...", file=sys.stderr)
        return False
    
    print(f"✓ Issue #{issue_number} 包含所有预期标签")
    
    # --------------------------
    # 步骤7：验证Issue评论合规性
    # --------------------------
    print(f"\n6/8 验证Issue评论（关联PR #{pr_number}）...")
    issue_comments = _get_issue_comments(issue_number, headers, github_org, CONFIG["target_repo"])
    valid_comment_found = False
    
    for comment in issue_comments:
        comment_body = comment.get("body", "").lower()
        
        # 1. 校验评论是否包含PR关联标识（如"PR #123"）
        expected_pr_ref = CONFIG["comment_requirements"]["pr_reference_flag"].format(pr_number=pr_number)
        if expected_pr_ref.lower() not in comment_body:
            continue
        
        # 2. 校验评论是否包含所有必需关键词
        has_all_keywords = all(
            kw.lower() in comment_body 
            for kw in CONFIG["comment_requirements"]["keywords"]
        )
        if not has_all_keywords:
            continue
        
        # 3. 校验评论是否包含所有必需内容标识
        has_all_flags = all(
            flag.lower() in comment_body 
            for flag in CONFIG["comment_requirements"]["content_flags"]
        )
        if has_all_flags:
            valid_comment_found = True
            break
    
    if not valid_comment_found:
        print(f"[错误] Issue #{issue_number} 未找到关联PR #{pr_number}的合规评论", file=sys.stderr)
        return False
    
    print(f"✓ Issue #{issue_number} 存在合规评论（关联PR #{pr_number}）")
    
    # --------------------------
    # 步骤8：验证标签文档与预期标签一致性
    # --------------------------
    print(f"\n7/8 验证标签文档与预期标签一致性...")
    
    # 1. 检查预期标签是否全部在文档中存在
    missing_in_doc = [
        lbl for lbl in CONFIG["expected_labels"] 
        if lbl not in documented_labels
    ]
    if missing_in_doc:
        print(f"[错误] 预期标签未全部出现在文档中：{missing_in_doc[:5]}...（共缺失{len(missing_in_doc)}个）", file=sys.stderr)
        return False
    
    # 2. 检查文档中是否存在未预期的标签（可选：根据项目需求决定是否保留）
    unexpected_in_doc = [
        lbl for lbl in documented_labels 
        if lbl not in CONFIG["expected_labels"]
    ]
    if unexpected_in_doc:
        print(f"[警告] 文档中存在未预期标签：{unexpected_in_doc[:3]}...（不影响验证通过，建议核对）")
    
    print(f"✓ 所有预期标签（共{len(CONFIG['expected_labels'])}个）均在文档中存在")
    
    # --------------------------
    # 步骤9：验证完成（补充步骤序号统一）
    # --------------------------
    print(f"\n8/8 所有验证步骤完成")
    print("\n" + "=" * 60)
    print("✅ 所有标签颜色标准化验证步骤通过！")
    print(f"验证对象：{github_org}/{CONFIG['target_repo']}")
    print(f"功能分支：{CONFIG['feature_branch']['name']}")
    print(f"验证Issue：#{issue_number}（{issue['title'][:30]}...）")
    print(f"验证PR：#{pr_number}（{pr['title'][:30]}...）")
    print("=" * 60)
    
    return True

# =============================================================================
# 脚本入口
# =============================================================================

if __name__ == "__main__":
    verification_result = verify_label_standardization()
    sys.exit(0 if verification_result else 1)  # 成功返回0，失败返回1
