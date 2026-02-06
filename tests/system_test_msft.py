import unittest
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
import sys

# Ensure modules are importable
sys.path.append(os.getcwd())

from modules.core.config import FINANCIAL_METRICS
import modules.core.db

class TestSystemMSFT(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # 1. Setup specific test DB
        cls.test_db_path = "test_system_msft.db"
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
            
        # Patch the DB_PATH in modules.db
        cls.db_patcher = patch('modules.core.db.DB_PATH', cls.test_db_path)
        cls.db_patcher.start()
        
        # Initialize DB
        from modules.core.db import init_db
        init_db()
        
    @classmethod
    def tearDownClass(cls):
        cls.db_patcher.stop()
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)

    def test_01_import_data(self):
        """Test importing MSFT_all.json into the DB"""
        json_path = os.path.join("upload", "MSFT_all.json")
        if not os.path.exists(json_path):
            print(f"Skipping test: {json_path} not found")
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            
        from modules.data.json_importer import import_json_to_database
        success, errors = import_json_to_database(json_data, "MSFT")
        
        print(f"Imported MSFT data: {success} records, {len(errors)} errors")
        if errors:
            print("Errors:", errors[:3])
            
        self.assertGreater(success, 0, "Should import at least 1 record")
        
        # Verify persistence
        conn = sqlite3.connect(self.test_db_path)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM financial_records WHERE ticker='MSFT'")
        count = c.fetchone()[0]
        conn.close()
        self.assertEqual(count, success)

    @patch('modules.valuation.valuation_PE.st')
    @patch('modules.core.db.get_market_history')
    def test_02_pe_valuation(self, mock_get_market, mock_st):
        """Test PE Valuation Tab with real MSFT data"""
        # Mock Market Data (5 years daily)
        dates = pd.date_range(start='2020-01-01', end='2024-12-31', freq='D')
        df_market = pd.DataFrame({
            'date': dates,
            'close': np.random.uniform(200, 400, size=len(dates)),
            'volume': 1000000
        })
        mock_get_market.return_value = df_market
        
        # Helper for columns
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            return m
        
        # Handle st.columns(3) or st.columns([1,2])
        mock_st.columns.side_effect = lambda spec: [create_col_mock() for _ in (range(spec) if isinstance(spec, int) else spec)]
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        
        # Load Data
        from modules.core.db import get_financial_records
        df_raw = pd.DataFrame(get_financial_records("MSFT"))
        
        from modules.valuation.valuation_PE import render_valuation_PE_tab
        try:
            render_valuation_PE_tab(df_raw, "Billion")
            print("PE Valuation Tab executed successfully")
        except Exception as e:
            self.fail(f"PE Valuation Tab failed: {e}")

    @patch('modules.valuation.valuation_DCF.st')
    def test_03_dcf_valuation(self, mock_st):
        """Test DCF Valuation Tab"""
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            return m
            
        mock_st.columns.side_effect = lambda spec: [create_col_mock() for _ in (range(spec) if isinstance(spec, int) else spec)]
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        
        from modules.core.db import get_financial_records
        df_raw = pd.DataFrame(get_financial_records("MSFT"))
        
        from modules.valuation.valuation_DCF import render_valuation_DCF_tab
        try:
            render_valuation_DCF_tab(df_raw, 0.08, 0.04, "Billion")
            print("DCF Valuation Tab executed successfully")
        except Exception as e:
            self.fail(f"DCF Valuation Tab failed: {e}")

    @patch('modules.valuation.valuation_advanced.st')
    @patch('modules.core.db.get_company_meta')
    @patch('modules.core.db.get_market_history')
    def test_04_advanced_models(self, mock_market, mock_meta, mock_st):
        """Test Advanced Models Tab"""
        mock_meta.return_value = {'last_market_cap': 3000*1e9, 'sector': 'Technology'}
        mock_market.return_value = pd.DataFrame({'date':['2024-01-01'], 'close':[400]})
        
        # Mocks
        mock_st.tabs.return_value = [MagicMock() for _ in range(6)]
        
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            m.slider.side_effect = lambda label, min_value=0.0, max_value=100.0, value=0.0, **kwargs: float(value)
            m.selectbox.side_effect = lambda label, options, index=0, **kwargs: options[index] if options else None
            return m
            
        mock_st.columns.side_effect = lambda spec: [create_col_mock() for _ in (range(spec) if isinstance(spec, int) else spec)]
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        mock_st.slider.side_effect = lambda label, min_value=0.0, max_value=100.0, value=0.0, **kwargs: float(value)
        
        def side_effect_selectbox(label, options, index=0, **kwargs):
             return options[index] if options else None
        mock_st.selectbox.side_effect = side_effect_selectbox
        
        from modules.core.db import get_financial_records
        df_raw = pd.DataFrame(get_financial_records("MSFT"))
        
        from modules.valuation.valuation_advanced import render_advanced_valuation_tab
        try:
            render_advanced_valuation_tab(df_raw, "Billion", 0.08, 0.04)
            print("Advanced Valuation Tab executed successfully")
        except Exception as e:
            self.fail(f"Advanced Valuation Tab failed: {e}")

if __name__ == '__main__':
    unittest.main()
