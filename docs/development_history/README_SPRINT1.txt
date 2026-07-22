SPRINT 1 — M5 FOUNDATION

Copy the folder "reality_calibration" into the root of your project.
Keep the M5 files here:

reality_calibration\data\m5\sales_train_validation.csv
reality_calibration\data\m5\calendar(1).csv
reality_calibration\data\m5\sell_prices.csv

From the project root, run:

powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT1.ps1

Or run directly:

python -m reality_calibration.scripts.analyze_m5 --data-dir .\reality_calibration\data\m5

Expected result:
- status = PASSED
- a JSON report written to:
  reality_calibration\data\processed\m5_quality_report.json
