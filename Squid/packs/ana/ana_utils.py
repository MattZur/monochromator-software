import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from pathlib import Path

def stability_analysis(
        save_name: str,
        overwrite: bool = False,
        no_show: bool = False,
        save: bool = True,
        ):
    '''
    For now only take the file and produce the full stability analysis report. 

    Output values are printed to the console and the plot is saved as a .png file. 
    '''
    # Set up the outpath for the figure
    out_path = Path(f"{save_name}_stability_analysis_report.png")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} exists; set overwrite = True to replace it.")

    # Load the file
    try:
        df = pd.read_csv(save_name)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {save_name}")

    # Convert timestamps to datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Extract date for the title
    experiment_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')

    duration_hours = df['t_min'].iloc[-1] / 60.0
    current_mean_total = df['current_mean_A'].mean()
    current_std_total = df['current_mean_A'].std()

    print("STABILITY REPORT")
    print(f"Total Duration: {duration_hours:.2f} hours")
    print(f"Global Mean Photocurrent: {current_mean_total:.6e} A")
    print(f"Global Std Dev of Photocurrent: {current_std_total:.6e} A")

    # Plotting
    fig, ax = plt.subplots(figsize=(11, 5.5))

    ax.errorbar(df['timestamp'], df['current_mean_A'], yerr=df['current_std_A'] / np.sqrt(df['n_samples']), color='#004488', linestyle='-', linewidth=1, fmt='o', markersize=3, elinewidth=1, capsize=2, label='Photocurrent (mean ± std)')

    ax.set_title(f'Deuterium Lamp Stability Test - 7.8 degrees - {experiment_date}', fontsize=14)
    ax.set_xlabel('Time of Day', fontsize=12, labelpad=10)
    ax.set_ylabel('Photocurrent (A)', fontsize=12, labelpad=10)
    ax.set_yscale('log')

    ax.grid(True, linestyle='--', alpha=0.5, color='#b0b0b0')

    # TIME AXIS FORMATTING (12-hour system, hour & half-hour ticks)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p'))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
    fig.autofmt_xdate(rotation=30, ha='right')

    if save:
        plt.savefig(f"{out_path}.png", dpi=600, bbox_inches='tight')

    plt.tight_layout()
    if not no_show:
        plt.show()
    return


def stability_analysis_volatility(
        save_name: str,
        overwrite: bool = False,
        no_show: bool = False,
        save: bool = True,
        filter_window: tuple[float, float] = (30.0, 1000.0),
        ):
    '''
    Take the stability file and produce the windowed linear fit and volatility report. 

    Output values are printed to the console and the plot is saved as a .png file. 
    '''
    # Set up the output path for the figure
    out_path = Path(f"{save_name}_stability_volatility_analysis_report.png")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} exists; set overwrite = True to replace it.")

    # Load the file
    try:
        df = pd.read_csv(save_name)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {save_name}")

    # Convert timestamps to datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Extract date for the title
    experiment_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')

    # Filter the data to cut off the 'warming-up' section
    df_filtered = df[df['t_min'] >= filter_window[0]].copy()
    df_filtered = df_filtered[df_filtered['t_min'] <= filter_window[1]].copy()

    # Caluculate linear fit and the slope in %
    # Convert filtered timestamps to numerical minutes/hours from the new start point
    time_minutes = df_filtered['t_min'].values - df_filtered['t_min'].min()
    time_hours = time_minutes / 60.0
    current_vals = df_filtered['current_mean_A'].values
    current_stds = df_filtered['current_std_A'] / np.sqrt(df_filtered['n_samples'])

    # Fit a first-degree polynomial (straight line): y = mx + c
    slope, intercept = np.polyfit(time_hours, current_vals, 1, w=1/current_stds)
    fit_line = slope * time_hours + intercept

    # Calculate relative slope percentage based on the global mean of this window
    mean_current = np.mean(current_vals)
    slope_pct_per_hour = (slope / mean_current) * 100
    slope_pct_per_minute = slope_pct_per_hour / 60.0

    print("LINEAR FIT REPORT")
    print(f"New Start Time: {df_filtered['timestamp'].iloc[0].strftime('%I:%M %p')}")
    print(f"New End Time: {df_filtered['timestamp'].iloc[-1].strftime('%I:%M %p')}")
    print(f"Mean Current (Filtered Window): {mean_current:.6e} A")
    print(f"Absolute Slope: {slope:.6e} A/hour")
    print(f"Relative Slope (%): {slope_pct_per_hour:.4f} % per hour")
    print(f"Relative Slope (%): {slope_pct_per_minute:.6f} % per minute")

    # Compute the step-by-step differences
    step_diffs = np.diff(current_vals)
    relative_diffs_pct = (step_diffs / current_vals[:-1]) * 100
    mean_step = np.mean(relative_diffs_pct)
    std_step = np.std(relative_diffs_pct)

    print("\nSTEP-TO-STEP VOLATILITY REPORT")
    print(f"Number of steps analyzed: {len(relative_diffs_pct)}")
    print(f"Average step variation: {mean_step:+.4f} %")
    print(f"Step variation standard deviation: {std_step:.4f} %")

    # Plotting
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={'width_ratios': [2, 1.2]})

    # LEFT PLOT: (Windowed) Long-term Time Evolution & Drift
    ax1.set_yscale('log')
    ax1.errorbar(df_filtered['timestamp'], current_vals, yerr=current_stds, color='#004488', linestyle='-', linewidth=1, fmt='o', markersize=3, elinewidth=1, capsize=2, label='Photocurrent')
    ax1.plot(df_filtered['timestamp'], fit_line, color='#e32219', linestyle='-', linewidth=1.5,
            label=f'Linear Fit ({slope_pct_per_hour:+.3f}% / hr)')


    ax1.set_title(f'Deuterium Lamp Stability & Linear Fit — {experiment_date}', fontsize=14)
    ax1.set_xlabel('Time of Day', fontsize=12, labelpad=10)
    ax1.set_ylabel('Photocurrent (A) — Log Scale', fontsize=12, labelpad=10)
    ax1.grid(True, which="both", linestyle='--', alpha=0.5, color='#b0b0b0')

    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p'))
    ax1.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
    ax1.tick_params(axis='x', rotation=30)
    ax1.legend(loc='upper left', frameon=True, edgecolor='#b0b0b0')

    # RIGHT PLOT: Short-term Step Volatility Histogram
    counts, bins, patches = ax2.hist(relative_diffs_pct, bins=25, color='#004488',
                                    edgecolor='white', alpha=0.85, rwidth=0.9)
    ax2.axvline(mean_step, color='#e32219', linestyle='--', linewidth=1.5,
            label=f'Mean Step \n({mean_step:+.3f}%)')

    ax2.set_title('Step-by-Step $\\sigma$ Distribution', fontsize=14)
    ax2.set_xlabel('Relative Variation vs Previous Point (%)', fontsize=12, labelpad=10)
    ax2.set_ylabel('Frequency (Count)', fontsize=12, labelpad=10)
    ax2.grid(True, linestyle='--', alpha=0.5, color='#b0b0b0')
    ax2.legend(loc='upper right', frameon=True, edgecolor='#b0b0b0')

    stats_box = f"$\\sigma$: {std_step:.3f}% \nSteps count: {len(relative_diffs_pct)}"
    ax2.text(0.05, 0.95, stats_box, transform=ax2.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='#b0b0b0', alpha=0.8))

    plt.tight_layout()

    if save:
        plt.savefig(f"{out_path}.png", dpi=600, bbox_inches='tight')

    plt.tight_layout()

    if not no_show:
        plt.show()
  
    return 