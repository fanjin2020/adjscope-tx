# AdjScope-Tx

统一入口为 `python run.py`，完成计算、论文CSV导出和图件绘制。

## 服务器全量分析

在代码目录中启用已安装、符合锁定版本的环境。运行时不自动安装依赖。

没有兼容的Python环境时，用现有Python 3.12显式配置独立环境：

```bash
python run.py setup-python --output "$HOME/adjscope/python330"
"$HOME/adjscope/python330/environment/bin/python" run.py run --output "$HOME/adjscope/p1_full" --workers 36
```

配置命令按两份requirements文件安装依赖，包括读取原始Excel样本表和表达矩阵所需的openpyxl。
不修改现有Python或R环境。已配置成功的环境仅校验和复用，不重新安装；环境发生变化时停止，不原地修复。
安装日志和ready.json保存在独立环境目录，不进入论文结果。加`--check-only`只校验、不安装。
服务器启动器也支持`--setup-python --python-env DIRECTORY`，配置后直接启动分析；
不能与`--resume`或`--plan`同时使用，R环境仍需预先符合要求。

```bash
conda activate paper1
python run.py run --output "$HOME/adjscope/p1_full" --workers 36 --check-env
python run.py run --output "$HOME/adjscope/p1_full" --workers 36
```

同一次运行完成计算、`results/` CSV导出和 `figures/` 图件生成；两类输出核验通过后才报告完成。
流程与最终论文一致：公共数据分析、设计信息与模型比较、计数配对校准、尾部校准。
这些是框架内部的分析模块，不需要分别启动补充实验或修补脚本。
全量计数实验可能运行数天；输出目录必须在代码目录之外。

```bash
python run.py status --output "$HOME/adjscope/p1_full"
python run.py run --resume --output "$HOME/adjscope/p1_full" --workers 36
```

断点恢复核验任务回执，只有 `job.json` 不算完成。
绘图中断可以用同一个恢复命令继续，不重新计算已经核验通过的模型任务。
旧实验继续用其原代码；不能把不同源代码或环境产生的任务混入同一实验。

全部分析阶段和CSV已完成、仅绘图未完成时，可使用框架内的导出入口：

```bash
python run.py finalize --output "$HOME/adjscope/p1_full"
```

该命令核对阶段完成状态、CSV及其分析输入的校验值，只生成图件，不下载、不拟合。
原分析源码身份保持不变，绘图和框架入口的变动另行记录；统计分析代码变动会被拒绝。
旧运行若没有逐文件源码记录，需要加`--analysis-source-manifest ORIGINAL_SOURCE_MANIFEST.json`，
该清单必须在修改前从原代码生成，并与原运行的源码校验值一致。不要手动更换校验值。

## 已有结果直接导出

将下面变量设为四项实验实际完成的目录，无需重跑模型：

```bash
python run.py report --study "$STUDY_RUN" --design "$DESIGN_RUN" \
  --counts "$COUNT_RUN" --tails "$TAIL_RUN" --output "$HOME/adjscope/p1_results"
python run.py figures --source "$HOME/adjscope/p1_results" --output "$HOME/adjscope/p1_figures"
```

新框架运行目录也可用 `report --source RUN --output NEW_DIR` 导出。
源文件缺失或校验失败会停止，不会用包内论文数值补齐。
旧尾部结果若缺少Gaussian几何汇总，需要已安装的R环境，仅补算设计几何。

## 默认输出

- `tables/Table1.csv` 至 `Table3.csv`：正文三张表，数量从当前结果汇总，解释文字遵循论文方案。
- `tables/TableS1.csv` 至 `TableS23.csv`：98个论文表格区块，用 `section` 列区分。
- `figure_data/*.csv`：表格之外必需的绘图数据，已在表格中的相同数据不重复导出。
- `manifest.csv`：表号、图号、文件、列类型、记录数、来源和校验值的统一映射。

完整导出固定为35个CSV：3个正文表、23个补充表、8个必需绘图数据及1个清单。
图表复用关系由论文清单明确规定，不再由浮点数是否完全相等决定。
S20.7与S17.7是同一份运行配置，清单保留两个表号，数值仅保存一份。
缺少阶段时只导出对应内容；缺表、清单漏项和未登记文件都会停止核验。
不导出逐次模拟明细、历史报告、自动解释文稿、重复Excel或审阅ZIP。
断点所需任务、日志和源数据仍保留在运行目录，不进入 `results/`。

全量运行默认在 `figures/` 输出10张主图和15张补图的PDF，以及2个环境和版面核验文件。
单独重绘时，`figures` 命令可加 `--tiff` 生成600 dpi TIFF，或加 `--editable` 生成SVG/PNG。

补充材料对应关系：ESM_1的补图由 `figures` 生成，方法说明仍是作者撰写的投稿文档；
ESM_2的98个表格区块由上述CSV及清单完整提供，不再额外导出一份重复Excel；
ESM_3使用本框架发布压缩包。框架不自动改写主稿或补充方法正文。

## 论文固定数值复现

```bash
python run.py verify
python run.py report --kind publication --output "$HOME/adjscope/p1_evidence"
python run.py figures --source "$HOME/adjscope/p1_evidence" --output "$HOME/adjscope/p1_replay_figures"
python run.py test
```

`publication` 明确使用包内记录的论文结果，不代表重跑实验。
API `diagnose_design` 和 `compare_models` 可用于自己的数据。
全量科研复算要求锁定的Linux环境；本地可核验CSV、接口和图件。许可证：MIT。
