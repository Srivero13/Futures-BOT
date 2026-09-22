# Parallel CPU and GPU research

This optional experiment compares degree-two polynomial ridge on the CPU with a
small neural network on CUDA. It does not accelerate or approve the live bot.
Both backends separately compare six candle features against nine candle-plus-flow
features on identical timestamps. The four May–August development folds remain
unchanged. September is reserved. Previously inspected periods are not untouched.

The network has hidden layers 32 and 16 with tanh, float32, AdamW (learning rate
0.001, weight decay 0.01), batch size 256, seed 1729 and exactly 40 epochs.
Scaling and target normalization use the training month only. No test or
calibration loss selects epochs. GPU results may vary across hardware/software.
The polynomial expands training-standardized features to all degree-two terms,
then uses the existing training-only standardized ridge solver with alpha 10.
Different architectures mean this is not a CPU-versus-GPU speed benchmark.

## Setup

Use a separate environment so optional GPU dependencies do not change the bot:

```bash
cd ~/projects/Futures-BOT
source .venv/bin/activate
python -m venv .venv-gpu
.venv-gpu/bin/python -m pip install -r requirements.txt
.venv-gpu/bin/python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cu118
nvidia-smi
```

The CUDA 11.8 build is listed in the official
[PyTorch version instructions](https://pytorch.org/get-started/previous-versions/).
A working NVIDIA driver is required. The launcher performs a real CUDA
forward/backward optimization step, and stops on incompatibility. It does not
install or modify drivers. CUDA execution must be verified on the target PC;
CPU tests alone cannot certify it.

```bash
.venv-gpu/bin/python -u parallel_research.py \
  --audit-dir data/YOUR-COMPLETED-ROLLING-BATCH \
  --output-dir data/parallel-research-run1
```

Supply the directory containing the six March–August ETH alignment reports.
No downloads are repeated. Run inside tmux for terminal persistence. Two workers
run concurrently per fold, each limited to two BLAS/OMP threads. Logs and JSON
reports are separate. Worker errors stop later folds; interruption terminates
children. Use a new output directory to rerun. No checkpoint resume is provided.

Watch the printed log paths for epoch progress. Each completed JSON contains
RMSE against zero, Spearman correlation and calibration-defined buckets.
Nothing here estimates executable P&L, saves a deployable model, selects a winner
or sends orders. Small datasets may finish quickly and underutilize the GPU.

## Learning controls

`python -m unittest discover -s tests -p test_parallel_learning.py -v` checks
raw flow/candle construction, timing and exact labels with a known synthetic
signal, a shuffled-label negative control, nonlinear polynomial recovery, and
(optional PyTorch) neural learning on CPU. Real-world profitability does not
follow from passing these controls.
