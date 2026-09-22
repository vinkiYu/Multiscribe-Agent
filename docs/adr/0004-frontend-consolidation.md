# ADR-0004 前端收敛:单一 prototype,废弃旧 console 与仓库内打包前端

- 状态:已采纳
- 日期:2026-08-15 / 2026-09-22 补录
- 关联:commit `d8212cf`、`4218584`、`prototype/`、`.gitignore`(前端迁移遗留段)

## 背景

仓库先后出现过三个前端形态:①打包在仓库内的 `frontend/`(后被删除并 zip 备份);②根目录散落的旧 console 副本(`multiscribe-console`,P58-P63 期间在其上开发过 agents/chat/source-search/curation-quality 页面,从未入 git);③外层目录的 `multiscribe-prototype`(React 19 + Vite,13 页,真正的产品前端)。

## 决策

1. **唯一前端 = `prototype/`(multiscribe-prototype)**,2026-08-15 从外层迁入仓库并入库。
2. 旧 console 副本移出仓库做一次性备份(仓库外 `prototype-console-backup-20260815/`),**其上的 P58-P63 页面视为未完成工作,待在新 prototype 上重做**;node_modules 等可再生内容不随备份保留。
3. 仓库不保留任何前端 zip/构建产物;`dist/`、`node_modules/`、`.env.local`、`*.tsbuildinfo` 全部 gitignore。
4. 一次性补丁脚本(`apply_p62_4.py`/`apply_p63.py`/`fix_p63.py`,针对已删除的旧 console 的字符串替换)随清理移出版本库(git 历史可追溯)。

## 后果

- 前端有唯一事实源;P58-P63 的聊天/筛选前端能力需重做(独立工作线,未排期)。
- gitignore 中过时的 `logo.png` 根规则已随清理移除,logo 统一由 `docs/pic/` 与 `prototype/public/` 管理。
