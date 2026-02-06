# modules/valuation_analyst.py
# 分析师预测分析模块
# v1.1 - 使用 yfinance 替代 Finnhub

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

from modules.data.analyst_fetcher import (
    get_analyst_fetcher,
    get_cached_price_target,
    get_cached_eps_estimates,
    get_cached_revenue_estimates,
    get_cached_recommendations
)
from modules.core.db import get_market_history, get_financial_records
from modules.core.calculator import process_financial_data


def render_analyst_tab(selected_company: str, df_raw: pd.DataFrame):
    """渲染分析师预测分析 Tab
    
    Args:
        selected_company: 当前选中的公司代码
        df_raw: 原始财务数据 DataFrame
    """
    st.subheader("📊 分析师预测分析")
    
    # --- 同步按钮 ---
    col_sync, col_status = st.columns([1, 3])
    with col_sync:
        if st.button("🔄 同步分析师数据", help="从 Yahoo Finance 获取最新分析师预测数据"):
            _sync_analyst_data(selected_company)
    
    with col_status:
        # 显示缓存状态
        cached_pt = get_cached_price_target(selected_company)
        if cached_pt:
            st.caption(f"📅 数据更新时间: {cached_pt.get('last_updated', 'N/A')}")
        else:
            st.caption("⚠️ 暂无缓存数据，请点击同步按钮获取")
    
    st.markdown("---")
    
    # --- 分 Tab 展示各类分析 ---
    st.markdown("---")
    
    # --- 简化版：统一 Tab 展示 ---
    # 需求：将 "目标价分析" 和 "推荐趋势" 合并
    # 需求：删除 "Forward Estimates" 和 "预测 vs 实际"
    
    _render_consolidated_analyst_view(selected_company)


def _sync_analyst_data(symbol: str):
    """同步分析师数据"""
    with st.spinner(f"正在从 Yahoo Finance 获取 {symbol} 的分析师数据..."):
        fetcher = get_analyst_fetcher()
        results = fetcher.fetch_all_analyst_data(symbol)
        
        errors = results.get('errors', [])
        if errors:
            for err in errors:
                st.warning(err)
        
        # 只要有一项成功就算成功
        if results.get('price_target') or results.get('recommendations'):
            st.success(f"✅ {symbol} 分析师数据已更新")
            st.rerun()
        elif not errors:
            st.warning("未获取到有效数据")


def _render_consolidated_analyst_view(symbol: str):
    """渲染合并后的分析师观点 (目标价 + 推荐趋势)"""
    col_target, col_rec = st.columns([1, 1])
    
    # === 左侧：目标价分析 ===
    with col_target:
        st.markdown("#### 🎯 目标价共识 (Target Price)")
        cached_pt = get_cached_price_target(symbol)
        
        if not cached_pt:
            st.info("暂无目标价数据")
        else:
            # 获取当前股价
            df_market = get_market_history(symbol)
            current_price = None
            if not df_market.empty:
                current_price = df_market.iloc[-1]['close']
            
            target_high = cached_pt.get('target_high', 0) or 0
            target_low = cached_pt.get('target_low', 0) or 0
            target_mean = cached_pt.get('target_mean', 0) or 0
            target_median = cached_pt.get('target_median', 0) or 0
            
            # 指标卡片
            c1, c2 = st.columns(2)
            c1.metric("平均目标价", f"${target_mean:.2f}")
            if current_price and target_mean:
                upside = ((target_mean - current_price) / current_price) * 100
                c2.metric("潜在空间", f"{upside:+.1f}%", delta_color="normal")
            
            # 可视化仪表盘/区间图
            fig = go.Figure()
            # 目标价区间 (Bar)
            fig.add_trace(go.Bar(
                x=['目标价区间'],
                y=[target_high - target_low],
                base=[target_low],
                marker_color='rgba(200, 200, 200, 0.3)',
                name='区间 (Low-High)',
                width=0.3
            ))
            # 均值点
            fig.add_trace(go.Scatter(
                x=['目标价区间'], y=[target_mean],
                mode='markers', marker=dict(color='blue', size=15, symbol='diamond'),
                name='平均目标价'
            ))
            # 当前价线
            if current_price:
                fig.add_hline(y=current_price, line_dash="dash", line_color="orange", 
                              annotation_text=f"当前 ${current_price:.2f}")
            
            fig.update_layout(title="目标价 vs 当前价", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            # 分歧指数
            if target_mean > 0:
                divergence = ((target_high - target_low) / target_mean) * 100
                st.caption(f"💡 分析师分歧度: {divergence:.1f}%")

    # === 右侧：推荐趋势 (混合图表) ===
    with col_rec:
        st.markdown("#### 📊 评级趋势 (Recommendations)")
        trends = get_cached_recommendations(symbol)
        
        if not trends:
            st.info("暂无评级数据")
            return
            
        df_trends = pd.DataFrame(trends)
        if df_trends.empty:
            st.info("评级数据为空")
            return
            
        # 排序
        if 'period' in df_trends.columns:
            df_trends = df_trends.sort_values('period')
            
        # 计算综合评分 (买入倾向)
        # 定义加权分: Strong Buy=5, Buy=4, Hold=3, Sell=2, Strong Sell=1
        def calc_score(row):
            total = row.get('strong_buy',0) + row.get('buy',0) + row.get('hold',0) + row.get('sell',0) + row.get('strong_sell',0)
            if total == 0: return 0
            score = (row.get('strong_buy',0)*5 + row.get('buy',0)*4 + row.get('hold',0)*3 + 
                     row.get('sell',0)*2 + row.get('strong_sell',0)*1) / total
            return score
            
        df_trends['score'] = df_trends.apply(calc_score, axis=1)
        
        # 自动分析文本
        latest_trend = df_trends.iloc[-1]
        latest_score = latest_trend['score']
        prev_score = df_trends.iloc[-2]['score'] if len(df_trends) >= 2 else latest_score
        
        analysis_text = f"当前综合评分为 **{latest_score:.2f}/5.0**。"
        if latest_score >= 4.5:
            analysis_text += " 分析师一致**强力推荐 (Strong Buy)**。"
        elif latest_score >= 3.5:
            analysis_text += " 整体倾向于**买入 (Buy)**。"
        elif latest_score >= 2.5:
            analysis_text += " 整体观点为**持有 (Hold)**。"
        else:
            analysis_text += " 整体倾向于**卖出 (Sell)**。"
            
        if latest_score > prev_score + 0.1:
            analysis_text += " 近期评级**有所上调** 📈。"
        elif latest_score < prev_score - 0.1:
            analysis_text += " 近期评级**有所下调** 📉。"
        else:
            analysis_text += " 评级趋势**保持稳定**。"
            
        st.info(f"💡 {analysis_text}")
        
        # 1. 趋势折线图 (显示综合评分趋势)
        fig_rec = go.Figure()
        
        # 综合评分线
        fig_rec.add_trace(go.Scatter(
            x=df_trends['period'], y=df_trends['score'],
            mode='lines+markers', name='综合评分',
            line=dict(color='#22c55e', width=3),
            marker=dict(size=8)
        ))
        
        fig_rec.update_layout(
            title="分析师评级趋势 (5=Strong Buy, 1=Strong Sell)", 
            xaxis_title="期间 (Period)",
            yaxis_title="综合评分",
            yaxis_range=[1, 5.5],
            height=250,
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_rec, use_container_width=True)
        
        # 2. 数据表格 (详细分布)
        st.markdown("##### 📋 评级分布明细")
        cols = ['period', 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell']
        valid_cols = [c for c in cols if c in df_trends.columns]
        
        col_map = {
            'period': '期间',
            'strong_buy': '强买 (5)', 'buy': '买入 (4)',
            'hold': '持有 (3)', 'sell': '卖出 (2)', 'strong_sell': '强卖 (1)'
        }
        
        st.dataframe(
            df_trends[valid_cols].rename(columns=col_map),
            use_container_width=True,
            hide_index=True
        )
