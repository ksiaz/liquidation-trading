import pandas as pd

df = pd.read_csv('optimization_results.csv')

# Filter configs with signals
configs_with_signals = df[df['signals'] > 0].sort_values('net_pnl', ascending=False)

print('\n' + '='*120)
print('CONFIGS THAT GENERATED SIGNALS (Sorted by Net PnL)')
print('='*120)
print(f"{'Rank':<6} {'Config':<8} {'SNR':<6} {'MinSig':<8} {'Conf':<6} {'Exit':<18} {'Sigs':<6} {'Trades':<8} {'WR%':<8} {'PnL%':<10}")
print('-'*120)

for idx, (_, row) in enumerate(configs_with_signals.iterrows(), 1):
    print(f"{idx:<6} #{row['config_num']:<7} {row['snr_threshold']:<6.1f} {row['min_signals']:<8} "
          f"{int(row['confidence_filter']):<6} {row['exit_strategy']:<18} {int(row['signals']):<6} "
          f"{int(row['trades']):<8} {row['win_rate']:<8.1f} {row['net_pnl']:+.2f}")

print('='*120)
print(f'\nSUMMARY:')
print(f'  Total configs tested: {len(df)}')
print(f'  Configs with 0 signals: {len(df[df["signals"] == 0])} ({len(df[df["signals"] == 0])/len(df)*100:.1f}%)')
print(f'  Configs with signals: {len(df[df["signals"] > 0])} ({len(df[df["signals"] > 0])/len(df)*100:.1f}%)')
print(f'\n  Best PnL: {configs_with_signals.iloc[0]["net_pnl"]:.2f}% (Config #{int(configs_with_signals.iloc[0]["config_num"])})')
print(f'  Worst PnL: {configs_with_signals.iloc[-1]["net_pnl"]:.2f}% (Config #{int(configs_with_signals.iloc[-1]["config_num"])})')
print()
