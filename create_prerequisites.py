#!/usr/bin/env python3
# =============================================================================
# GitHub工作流合规性验证脚本
# 验证目标仓库的CI/CD工作流是否符合预设规范
# 依赖：requests, python-dotenv（安装：pip install requests python-dotenv）
# =============================================================================
import sys
import os
import requests
import json
import base64
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# =============================================================================
# 配置部分 - 根据项目需求修改以下配置
# =============================================================================
CONFIG = {
    # 目标仓库信息
    "target_repo": "label-project",  # 替换为实际仓库名
    
    # 功能分支配置
    "feature_branch": {
        "name": "feature/ci-cd-workflow",  # 功能分支名
        "doc_file": "docs/workflow-compliance.md"  # 工作流文档路径
    },
    
    # 文档解析配置
    "doc_parsing": {
        "table_header": "| Workflow Step | Status | Owner |",  # 文档表格头部
        "min_step_count": 5  # 文档至少包含的工作流步骤数
    },
   
    # Issue验证配置
    "issue_requirements": {
        "title_keywords": ["Implement CI/CD workflow", "Workflow automation"],  # Issue标题关键词
        "body_keywords": ["automate", "CI/CD workflow", "CI/CD pipeline"],  # Issue内容关键词
        "required_sections": ["## Problem Statement", "## Proposed Solution", "## Implementation Plan"],  # Issue必需章节
        "initial_labels": ["enhancement", "automation"]  # Issue初始必需标签
    },
    
    # PR验证配置
    "pr_requirements": {
        "title_keywords": ["Add CI/CD workflow", "Workflow implementation"],  # PR标题关键词
        "body_keywords": ["workflow implementation", "reference issue #", "CI/CD pipeline"],  # PR内容关键词
        "required_sections": ["## Summary", "## Changes", "## Testing"],  # PR必需章节
        "min_labels_count": 3,  # PR至少需包含的标签数量
        "issue_reference_pattern": "Closes #{issue_number}"  # PR关联Issue的格式
    },
    
    # 预期工作流步骤配置
    "expected_workflow_steps": [
        "Code checkout", "Dependency installation", "Unit testing", 
        "Integration testing", "Build artifact", "Deploy staging", 
        "Deploy production", "Health check"
    ],
    
    # Issue评论验证配置
    "comment_requirements": {
        "keywords": ["workflow implemented", "pipeline tested", "deployment verified"],  # 评论必需关键词
        "pr_reference_flag": "PR #{pr_number}",  # 评论关联PR的格式
        "content_flags": ["8 steps", "all environments", "success rate"]  # 评论必需内容标识
    }
}

# =============================================================================
# 通用工具函数
# =============================================================================
def _get_github_api(endpoint: str, headers: Dict[str, str], org: str, repo: str) -> Tuple[bool, Optional[Dict]]:
    """通用GitHub API请求函数"""
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

def _check_branch_exists(branch_name: str, headers: Dict[str, str], org: str, repo: str) -> bool:
    """验证目标分支是否存在"""
    success, _ = _get_github_api(f"branches/{branch_name}", headers, org, repo)
    return success

def _get_file_content(branch: str, file_path: str, headers: Dict[str, str], org: str, repo: str) -> Optional[str]:
    """从指定分支获取文件内容（Base64解码）"""
    success, result = _get_github_api(f"contents/{file_path}?ref={branch}", headers, org, repo)
    if not success or not result:
        return None
    if result.get("content"):
        try:
            return base64.b64decode(result["content"]).decode("utf-8")
        except Exception as e:
            print(f"[文件解码错误] {file_path}：{str(e)}", file=sys.stderr)
            return None
    return None

def _parse_workflow_table(content: str, table_header: str) -> List[str]:
    """从Markdown内容中提取工作流步骤"""
    workflow_steps = []
    lines = content.split("\n")
    in_table = False
    
    for line in lines:
        # 识别表格头部
        if table_header in line:
            in_table = True
            continue
            
        # 跳过表格分隔线
        if in_table and line.startswith("|---"):
            continue
            
        # 解析表格行
        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:  # 匹配"空|步骤名|状态|负责人|空"格式
                step_name = parts[1]
                if step_name:
                    workflow_steps.append(step_name)
                    
        # 识别表格结束
        if in_table and line and not line.startswith("|"):
            break
            
    return workflow_steps

def _find_issue_by_keywords(title_keywords: List[str], headers: Dict[str, str], org: str, repo: str) -> Optional[Dict]:
    """按标题关键词查找Issue"""
    for state in ["open", "closed"]:
        success, issues = _get_github_api(f"issues?state={state}&per_page=30", headers, org, repo)
        if success and issues:
            for issue in issues:
                # 跳过PR（仅匹配纯Issue）
                if "pull_request" in issue:
                    continue
                title = issue.get("title", "").lower()
                if all(kw.lower() in title for kw in title_keywords):
                    return issue
    return None

def _find_pr_by_keywords(title_keywords: List[str], headers: Dict[str, str], org: str, repo: str) -> Optional[Dict]:
    """按标题关键词查找PR"""
    for state in ["open", "closed"]:
        success, prs = _get_github_api(f"pulls?state={state}&per_page=30", headers, org, repo)
        if success and prs:
            for pr in prs:
                title = pr.get("title", "").lower()
                if all(kw.lower() in title for kw in title_keywords):
                    return pr
    return None

def _get_issue_comments(issue_number: int, headers: Dict[str, str], org: str, repo: str) -> List[Dict]:
    """获取指定Issue的所有评论"""
    success, comments = _get_github_api(f"issues/{issue_number}/comments", headers, org, repo)
    return comments if (success and comments) else []

# =============================================================================
# 核心验证流程
# =============================================================================
def verify_workflow_compliance() -> bool:
    """工作流合规性验证主流程"""
    # 步骤1：加载环境变量
    print("=" * 60)
    print("开始执行GitHub工作流合规性验证")
    print("=" * 60)
    
    load_dotenv(".env")
    github_token = os.environ.get("GITHUB_TOKEN")
    github_org = os.environ.get("GITHUB_ORG")
    
    # 校验环境变量
    if not github_token:
        print("[环境错误] 未配置 GITHUB_TOKEN（需在 .env 中设置）", file=sys.stderr)
        return False
    if not github_org:
        print("[环境错误] 未配置 GITHUB_ORG（需在 .env 中设置）", file=sys.stderr)
        return False
    
    # 构建API请求头
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    print(f"目标仓库：{github_org}/{CONFIG['target_repo']}")
    print("=" * 60)

    # 步骤2：验证功能分支存在性
    print(f"\n1/8 验证功能分支：{CONFIG['feature_branch']['name']}...")
    if not _check_branch_exists(
        CONFIG["feature_branch"]["name"], headers, github_org, CONFIG["target_repo"]
    ):
        print(f"[错误] 功能分支 {CONFIG['feature_branch']['name']} 未找到", file=sys.stderr)
        return False
    print(f"✓ 功能分支 {CONFIG['feature_branch']['name']} 存在")

    # 步骤3：验证工作流文档完整性
    print(f"\n2/8 验证工作流文档：{CONFIG['feature_branch']['doc_file']}...")
    doc_content = _get_file_content(
        branch=CONFIG["feature_branch"]["name"],
        file_path=CONFIG["feature_branch"]["doc_file"],
        headers=headers,
        org=github_org,
        repo=CONFIG["target_repo"]
    )
    if not doc_content:
        print(f"[错误] 工作流文档 {CONFIG['feature_branch']['doc_file']} 未找到", file=sys.stderr)
        return False
    
    # 解析文档中的工作流步骤
    workflow_steps = _parse_workflow_table(
        content=doc_content,
        table_header=CONFIG["doc_parsing"]["table_header"]
    )
    if len(workflow_steps) < CONFIG["doc_parsing"]["min_step_count"]:
        print(f"[错误] 工作流步骤数量不足：实际 {len(workflow_steps)} 个，需至少 {CONFIG['doc_parsing']['min_step_count']} 个", file=sys.stderr)
        return False
    print(f"✓ 工作流文档存在，共包含 {len(workflow_steps)} 个步骤")

    # 步骤4：验证Issue创建与合规性
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

    # 步骤5：验证PR创建与合规性
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

    # 步骤6：验证Issue标签完整性
    print(f"\n5/8 验证Issue标签完整性...")
    # 这里我们假设Issue应该包含所有工作流相关的标签
    expected_issue_labels = ["workflow", "automation", "ci-cd", "enhancement"]
    missing_issue_all_labels = [
        lbl for lbl in expected_issue_labels 
        if lbl not in issue_labels
    ]
    if missing_issue_all_labels:
        print(f"[错误] Issue缺失 {len(missing_issue_all_labels)} 个预期标签：{missing_issue_all_labels}", file=sys.stderr)
        return False
    print(f"✓ Issue #{issue_number} 包含所有预期标签")

    # 步骤7：验证Issue评论合规性
    print(f"\n6/8 验证Issue评论（关联PR #{pr_number}）...")
    issue_comments = _get_issue_comments(issue_number, headers, github_org, CONFIG["target_repo"])
    valid_comment_found = False
    
    for comment in issue_comments:
        comment_body = comment.get("body", "").lower()
        
        # 校验评论是否包含PR关联标识
        expected_pr_ref = CONFIG["comment_requirements"]["pr_reference_flag"].format(pr_number=pr_number)
        if expected_pr_ref.lower() not in comment_body:
            continue
        
        # 校验评论是否包含所有必需关键词
        has_all_keywords = all(
            kw.lower() in comment_body 
            for kw in CONFIG["comment_requirements"]["keywords"]
        )
        if not has_all_keywords:
            continue
        
        # 校验评论是否包含所有必需内容标识
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

    # 步骤8：验证工作流文档与预期步骤一致性
    print(f"\n7/8 验证工作流文档与预期步骤一致性...")
    # 检查预期步骤是否全部在文档中存在
    missing_in_doc = [
        step for step in CONFIG["expected_workflow_steps"] 
        if step not in workflow_steps
    ]
    if missing_in_doc:
        print(f"[错误] 预期工作流步骤未全部出现在文档中：{missing_in_doc}", file=sys.stderr)
        return False
    
    # 检查文档中是否存在未预期的步骤（可选）
    unexpected_in_doc = [
        step for step in workflow_steps 
        if step not in CONFIG["expected_workflow_steps"]
    ]
    if unexpected_in_doc:
        print(f"[警告] 文档中存在未预期步骤：{unexpected_in_doc}（不影响验证通过，建议核对）")
    
    print(f"✓ 所有预期工作流步骤（共{len(CONFIG['expected_workflow_steps'])}个）均在文档中存在")

    # 步骤9：验证完成
    print(f"\n8/8 所有验证步骤完成")
    print("\n" + "=" * 60)
    print("✅ 所有工作流合规性验证步骤通过！")
    print(f"验证对象：{github_org}/{CONFIG['target_repo']}")
    print(f"功能分支：{CONFIG['feature_branch']['name']}")
    print(f"验证Issue：#{issue_number}（{issue['title'][:30]}...）")
    print(f"验证PR：#{pr_number}（{pr['title'][:30]}...）")
    print(f"工作流步骤：{len(workflow_steps)} 个")
    print("=" * 60)
    return True

# =============================================================================
# 脚本入口
# =============================================================================
if __name__ == "__main__":
    verification_result = verify_workflow_compliance()
    sys.exit(0 if verification_result else 1)  # 成功返回0，失败返回1