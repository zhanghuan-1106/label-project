# GitHub工作流合规性验证脚本
一个简单的GitHub工作流合规性验证工具，用于检查CI/CD工作流是否符合预设规范。

## 功能特点
- 验证功能分支和文档存在性
- 检查Issue和PR的合规性
- 验证标签和评论完整性
- 确保文档与预期步骤一致

## 安装
```bash
pip install requests python-dotenv
```

## 配置
创建 `.env` 文件：

```env
GITHUB_TOKEN=your_github_token
GITHUB_ORG=your_organization
```

## 使用
1. 修改脚本中的 `CONFIG` 配置以适应你的项目需求
2. 运行脚本：
```bash
python workflow-compliance-verification.py
```

## 输出
脚本会显示验证过程和结果：
- 成功时：✅ 所有工作流合规性验证步骤通过！
- 失败时：显示具体错误信息

## 验证流程
1. 环境配置验证
2. 功能分支验证
3. 工作流文档验证
4. Issue合规性验证
5. PR合规性验证
6. Issue标签完整性验证
7. Issue评论验证
8. 文档一致性验证

## 前置物料准备
在运行脚本前，确保GitHub仓库中包含：
- 功能分支（如 `feature/ci-cd-workflow`）
- 工作流文档（如 `docs/workflow-compliance.md`）
- 符合要求的Issue和PR
- Issue中的相关评论
