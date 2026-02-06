import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import os

# Ensure modules can be imported from root
sys.path.append(os.getcwd())

# Mock data generator
def create_mock_financial_data():
    dates = pd.date_range(start='2020-01-01', periods=8, freq='Q')
    df = pd.DataFrame({
        'ticker': ['TEST'] * 8,
        'report_date': dates,
        'year': dates.year,
        'period': ['Q1','Q2','Q3','Q4'] * 2,
        'EPS_TTM': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7],
        'EPS_TTM_YoY': [10.0] * 8,
        'TotalRevenue_TTM': [100.0] * 8,
        'NetIncome_TTM': [20.0] * 8,
        'FreeCashFlow_TTM': [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0],
        'FreeCashFlow_TTM_YoY': [0.1] * 8,
        'TotalDebt': [50.0] * 8,
        'CashAndEquivalents': [20.0] * 8,
        'TotalAssets': [200.0] * 8,
        'TotalEquity': [100.0] * 8,
        'CapEx': [-5.0] * 8,
        'OperatingCashFlow_TTM': [15.0] * 8,
        'EBITDA_TTM': [30.0] * 8,
        'OperatingProfit_TTM': [25.0] * 8,
        'GrossProfit_TTM': [60.0] * 8,
        'OperatingExpenses_TTM': [35.0] * 8 
    })
    return df

class TestValuationFeatures(unittest.TestCase):
    
    def setUp(self):
        # Create dummy data
        self.df_raw = create_mock_financial_data()
        self.mock_meta = {'last_market_cap': 100e9, 'sector': 'Technology'}
        self.mock_market = pd.DataFrame({
            'date': pd.date_range('2020-01-01', periods=100), 
            'close': [100.0]*100,
            'volume': [1000]*100
        })
        
        # Patch db calls globally for these modules
        self.patcher1 = patch('modules.db.get_company_meta', return_value=self.mock_meta)
        self.patcher2 = patch('modules.db.get_market_history', return_value=self.mock_market)
        self.patcher3 = patch('modules.risk_free_rate.get_risk_free_rate', return_value=0.04)
        
        self.mock_get_meta = self.patcher1.start()
        self.mock_get_market = self.patcher2.start()
        self.mock_get_rf = self.patcher3.start()
        
    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()

    @patch('modules.valuation_DCF.st')
    def test_dcf_model(self, mock_st):
        """Verify DCF Logic runs without error"""
        from modules.valuation_DCF import render_valuation_DCF_tab
        
        # Helper to create column mocks with configured inputs
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            return m

        # Configure st.columns to return list of mocks
        mock_st.columns.side_effect = lambda n: [create_col_mock() for _ in range(n)] if isinstance(n, int) else [create_col_mock() for _ in n]
        # Return default value for direct number_input
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        
        # WACC=0.08, RF=0.04
        render_valuation_DCF_tab(self.df_raw, 0.08, 0.04, "B")
        
        print("DCF Module executed successfully")

    @patch('modules.valuation_advanced.st')
    def test_advanced_models(self, mock_st):
        """Verify Advanced Models logic including PEG, EV/EBITDA, Monte Carlo"""
        from modules.valuation_advanced import render_advanced_valuation_tab
        
        # Mock tabs
        mock_tabs = [MagicMock() for _ in range(6)]
        mock_st.tabs.return_value = mock_tabs
        
        # Helper for columns
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            m.slider.side_effect = lambda label, min_value=0.0, max_value=100.0, value=0.0, **kwargs: float(value)
            
            # selectbox on column
            def side_effect_selectbox(label, options, index=0, **kwargs):
                 return options[index] if options else None
            m.selectbox.side_effect = side_effect_selectbox
            return m
        
        # Mock columns logic
        mock_st.columns.side_effect = lambda n: [create_col_mock() for _ in range(n)] if isinstance(n, int) else [create_col_mock() for _ in n]
        
        # Mock global inputs
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        mock_st.slider.side_effect = lambda label, min_value=0.0, max_value=100.0, value=0.0, **kwargs: float(value)
        
        # selectbox should return options[0] or index
        def side_effect_selectbox(label, options, index=0, **kwargs):
             return options[index]
        mock_st.selectbox.side_effect = side_effect_selectbox

        render_advanced_valuation_tab(self.df_raw, "B", 0.08, 0.04)
        print("Advanced Models module executed successfully")

    @patch('modules.valuation_PE.st')
    def test_pe_model(self, mock_st):
        """Verify PE Model Logic"""
        from modules.valuation_PE import render_valuation_PE_tab
        
        def create_col_mock():
            m = MagicMock()
            m.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
            return m
            
        mock_st.columns.side_effect = lambda n: [create_col_mock() for _ in range(n)] if isinstance(n, int) else [create_col_mock() for _ in n]
        mock_st.number_input.side_effect = lambda label, value=0.0, **kwargs: float(value)
        
        render_valuation_PE_tab(self.df_raw, "B")
        print("PE Module executed successfully")
        
    @patch('modules.valuation_analyst.st')
    @patch('modules.valuation_analyst.get_cached_price_target')
    @patch('modules.valuation_analyst.get_cached_recommendations')
    def test_analyst_overhaul(self, mock_get_rec, mock_get_pt, mock_st):
        """Verify Analyst Forecast Overhaul"""
        mock_get_pt.return_value = {'target_mean': 150.0, 'target_high': 160.0, 'target_low': 140.0}
        mock_get_rec.return_value = [{'period': '2024-03', 'buy': 10, 'hold': 5}]
        
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)] if isinstance(n, int) else [MagicMock() for _ in n]
        
        from modules.valuation_analyst import _render_consolidated_analyst_view
        _render_consolidated_analyst_view('TEST')
        print("Analyst Forecast Module executed successfully")

if __name__ == '__main__':
    unittest.main()
