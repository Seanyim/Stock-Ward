### macOS / Linux
source .venv/bin/activate

### Windows (PowerShell)
conda create -n my_project_env python=3.10
conda activate my_project_env


### library requirment
pip install pipreqs
pipreqs . --encoding=utf8 --force
pip install -r requirements.txt

### workflow
#### git
git clone <your-repo-url>
cd PriceEstimated

git status
git branch

git checkout -b feature/valuation-model

git add .
git commit -m "Add DCF & WACC valuation modules"

git pull origin main

git push origin feature/valuation-model


#### self-check
python -c "import sys, streamlit, pandas, numpy, plotly; print('Python:', sys.executable); print('Env check: OK')"


#### run
streamlit run main.py --server.port 8502
