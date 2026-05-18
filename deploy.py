# Railway 部署脚本
# 用法: python deploy.py
# 这个脚本会构建前端并将其复制到后端文件夹，然后准备部署

import subprocess
import shutil
import os
import sys

def run_cmd(cmd):
    print(f"运行: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        sys.exit(1)
    return result

# 1. 构建前端
print("=" * 50)
print("步骤 1: 构建前端 H5")
print("=" * 50)
run_cmd("npm run build:h5")

# 2. 复制前端到后端
print("=" * 50)
print("步骤 2: 复制前端到后端")
print("=" * 50)
backend_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dist = os.path.join(backend_dir, '..', '..', '..', '..', 'dist', 'build', 'h5')
frontend_dest = os.path.join(backend_dir, 'frontend')

if os.path.exists(frontend_dest):
    shutil.rmtree(frontend_dest)

shutil.copytree(frontend_dist, frontend_dest)
print(f"前端已复制到: {frontend_dest}")

# 3. 提交并推送到 GitHub
print("=" * 50)
print("步骤 3: 推送到 GitHub")
print("=" * 50)
print("请手动执行以下命令:")
print("  git add -A")
print("  git commit -m 'Update frontend and backend'")
print("  git push origin main")
print("=" * 50)
print("部署完成！请在 Railway 上重新部署")
print("=" * 50)
