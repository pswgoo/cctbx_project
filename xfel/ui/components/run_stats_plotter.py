from __future__ import division

from dials.array_family import flex
from matplotlib import pyplot as plt

# get_hitrate_stats takes a tuple (run, trial, rungroup, d_min)
# and returns a tuple of flex arrays as follows:
# time (s) -- flex.double, timestamp of the shot,
# ratio -- flex.double, ratio of intensities at two angles in the radial average
# n_strong -- flex.int, number of strong spots identified by hitfinder,
# I_sig_I_low -- flex.double, the average I/sig(I) in the low res bin of each shot, if it indexed
# I_sig_I_high -- flex.double, the average I/sig(I) in the high res bin of each shot, if it indexed

def get_should_have_indexed_timestamps(timestamps,
                                       n_strong,
                                       isigi_low,
                                       n_strong_cutoff):
  should_have_indexed_sel = (isigi_low == 0) & (n_strong >= n_strong_cutoff) # isigi = 0 if not indexed?
  should_have_indexed = timestamps.select(should_have_indexed_sel)
  return should_have_indexed

def get_multirun_should_have_indexed_timestamps(stats_by_run,
                                                run_numbers,
                                                d_min,
                                                n_strong_cutoff=40):
  timestamps = []
  for idx in xrange(len(stats_by_run)):
    r = stats_by_run[idx]
    if len(r[0]) > 0:
      timestamps.append(
        get_should_have_indexed_timestamps(r[0], r[3], r[4], n_strong_cutoff))
    else:
      timestamps.append(flex.double())
  return (run_numbers, timestamps)

def get_paths_from_timestamps(timestamps,
                              prepend="",
                              tag="idx"):
  import time, os, math
  def convert(s):
    time_seconds = int(math.floor(s))
    time_milliseconds = int(round((s - time_seconds)*1000))
    time_obj = time.gmtime(time_seconds)
    name = "%s-%04d%02d%02d%02d%02d%02d%03d.pickle" % (
      tag,
      time_obj.tm_year,
      time_obj.tm_mon,
      time_obj.tm_mday,
      time_obj.tm_hour,
      time_obj.tm_min,
      time_obj.tm_sec,
      time_milliseconds)
    return name
  names = map(convert, timestamps)
  paths = [os.path.join(prepend, name) for name in names]
  return paths

def get_run_stats(timestamps,
                   two_theta_low,
                   two_theta_high,
                   n_strong,
                   isigi_low,
                   isigi_high,
                   tuple_of_timestamp_boundaries,
                   lengths,
                   run_numbers,
                   ratio_cutoff=1,
                   n_strong_cutoff=40,
                   ):
  iterator = xrange(len(isigi_low))
  # hit rate of drops (observe solvent) or crystals (observe strong spots)
  # since -1 is used as a flag for "did not store this value", and we want a quotient,
  # set the numerator value to 0 whenever either the numerator or denominator is -1
  invalid = (two_theta_low <= 0) or (two_theta_high < 0) # <= to prevent /0
  numerator = two_theta_high.set_selected(invalid, 0)
  denominator = two_theta_low.set_selected(two_theta_low == 0, 1) # prevent /0
  drop_ratios = numerator/denominator
  drop_hits = drop_ratios >= ratio_cutoff
  xtal_hits = n_strong >= n_strong_cutoff
  # indexing and droplet hit rate in a sliding window
  half_idx_rate_window = min(50, int(len(isigi_low)//20))
  idx_low_sel = (isigi_low > 0) & (n_strong >= n_strong_cutoff)
  idx_high_sel = (isigi_high > 0) & (n_strong >= n_strong_cutoff)
  idx_rate = flex.double()
  drop_hit_rate = flex.double()
  for i in iterator:
    idx_min = max(0, i - half_idx_rate_window)
    idx_max = min(i + half_idx_rate_window, len(isigi_low))
    idx_span = idx_max - idx_min
    idx_sel = idx_low_sel[idx_min:idx_max]
    idx_local_rate = idx_sel.count(True)/idx_span
    idx_rate.append(idx_local_rate)
    drop_sel = drop_hits[idx_min:idx_max]
    drop_local_rate = drop_sel.count(True)/idx_span
    drop_hit_rate.append(drop_local_rate)
  return (timestamps,
          drop_ratios,
          drop_hits,
          drop_hit_rate,
          n_strong,
          xtal_hits,
          idx_rate,
          idx_low_sel,
          idx_high_sel,
          isigi_low,
          isigi_high,
          half_idx_rate_window*2,
          lengths,
          tuple_of_timestamp_boundaries,
          run_numbers)

def plot_run_stats(stats, d_min, run_tags=[], interactive=True, xsize=30, ysize=10):
  plot_ratio = max(min(xsize, ysize)/2.5, 3)
  t, drop_ratios, drop_hits, drop_hit_rate, n_strong, xtal_hits, \
  idx_rate, idx_low_sel, idx_high_sel, isigi_low, isigi_high, \
  window, lengths, boundaries, run_numbers = stats
  if len(t) == 0:
    return None
  max_idx_rate = max(idx_rate)
  max_drop_rate = max(drop_hit_rate)
  drop_rate_scaled = drop_hit_rate * max_idx_rate/max_drop_rate
  f, (ax1, ax2, ax3, ax4) = plt.subplots(4, sharex=True, sharey=False)
  for a in (ax1, ax2, ax3, ax4):
    a.tick_params(axis='x', which='both', bottom='off', top='off')
  ax1.scatter(t.select(~idx_low_sel), n_strong.select(~idx_low_sel), edgecolors="none", color ='grey', s=plot_ratio)
  ax1.scatter(t.select(idx_low_sel), n_strong.select(idx_low_sel), edgecolors="none", color='blue', s=plot_ratio)
  ax1.axis('tight')
  ax1.set_ylabel("strong spots\nblue: indexed\ngray: did not index").set_fontsize(3*plot_ratio)
  ax2.plot(t, idx_rate*100)
  ax2.plot(t, drop_rate_scaled*100, color='green')
  ax2.axis('tight')
  ax2.set_ylabel("green: droplet\nblue:indexed\n(arbitrary/%)").set_fontsize(3*plot_ratio)
  ax3.scatter(t, isigi_low, edgecolors="none", color='red', s=plot_ratio)
  ax3.scatter(t, isigi_high, edgecolors="none", color='orange', s=plot_ratio)
  ax3.axis('tight')
  ax3.set_ylabel("signal-to-noise\nred: low res\nyellow: %3.1f Ang" % d_min).set_fontsize(3*plot_ratio)
  for a in [ax1, ax2, ax3, ax4]:
    xlab = a.get_xticklabels()
    ylab = a.get_yticklabels()
    for l in xlab + ylab:
      l.set_fontsize(3*plot_ratio)
  f.subplots_adjust(hspace=0)
  # add lines and text summaries at the timestamp boundaries
  for boundary in boundaries:
    for a in (ax1, ax2, ax3):
      a.axvline(x=boundary, ymin=0, ymax=3, linewidth=1, color='k')
  run_starts = boundaries[0::2]
  run_ends = boundaries[1::2]
  start = 0
  end = -1
  for idx in xrange(len(run_numbers)):
    start_t = run_starts[idx]
    end_t = run_ends[idx]
    end += lengths[idx]
    slice_t = t[start:end+1]
    slice_hits = xtal_hits[start:end+1]
    n_hits = slice_hits.count(True)
    slice_drops = drop_hits[start:end+1]
    n_drops = slice_drops.count(True)
    slice_idx_low_sel = idx_low_sel[start:end+1]
    slice_idx_high_sel = idx_high_sel[start:end+1]
    n_idx_low = slice_idx_low_sel.count(True)
    n_idx_high = slice_idx_high_sel.count(True)
    tags = run_tags[idx] if idx < len(run_tags) else []
    ax4.text(start_t, 3.9, " " + ", ".join(tags)).set_fontsize(3*plot_ratio)
    ax4.text(start_t, .9, "run %d" % run_numbers[idx]).set_fontsize(3*plot_ratio)
    ax4.text(start_t, .7, "%d f/%d h" % (lengths[idx], n_hits)).set_fontsize(3*plot_ratio)
    ax4.text(start_t, .5, "%d (%d) idx" % (n_idx_low, n_idx_high)).set_fontsize(3*plot_ratio)
    ax4.text(start_t, .3, "%-3.1f%% drop/%-3.1f%% hit" % ((100*n_drops/lengths[idx]),(100*n_hits/lengths[idx]))).set_fontsize(3*plot_ratio)
    ax4.text(start_t, .1, "%-3.1f (%-3.1f)%% idx" % \
      (100*n_idx_low/lengths[idx], 100*n_idx_high/lengths[idx])).set_fontsize(3*plot_ratio)
    ax4.set_xlabel("timestamp (s)\n# images shown as all (%3.1f Angstroms)" % d_min).set_fontsize(3*plot_ratio)
    ax4.set_yticks([])
    for item in [ax1, ax2, ax3, ax4]:
      item.tick_params(labelsize=3*plot_ratio)
    start += lengths[idx]
  if interactive:
    def onclick(event):
      import math
      ts = event.xdata
      diffs = flex.abs(t - ts)
      ts = t[flex.first_index(diffs, flex.min(diffs))]
      print get_paths_from_timestamps([ts], tag="shot")[0]

    cid = f.canvas.mpl_connect('button_press_event', onclick)
    plt.show()
    f.canvas.mpl_disconnect(cid)
  else:
    f.set_size_inches(xsize, ysize)
    f.savefig("runstats_tmp.png", bbox_inches='tight', dpi=100)
    plt.close(f)
    return "runstats_tmp.png"

def plot_multirun_stats(runs,
                        run_numbers,
                        d_min,
                        ratio_cutoff=1,
                        n_strong_cutoff=40,
                        run_tags=[],
                        interactive=False,
                        compress_runs=True,
                        xsize=30,
                        ysize=10):
  tset = flex.double()
  two_theta_low_set = flex.double()
  two_theta_high_set = flex.double()
  nset = flex.int()
  I_sig_I_low_set = flex.double()
  I_sig_I_high_set = flex.double()
  boundaries = []
  lengths = []
  runs_with_data = []
  offset = 0
  for idx in xrange(len(runs)):
    r = runs[idx]
    if len(r[0]) > 0:
      if compress_runs:
        tslice = r[0] - r[0][0] + offset
        offset += (r[0][-1] - r[0][0])
      else:
        tslice = r[0]
      last_end = r[0][-1]
      tset.extend(tslice)
      two_theta_low_set.extend(r[1])
      two_theta_high_set.extend(r[2])
      nset.extend(r[3])
      I_sig_I_low_set.extend(r[4])
      I_sig_I_high_set.extend(r[5])
      boundaries.append(tslice[0])
      boundaries.append(tslice[-1])
      lengths.append(len(tslice))
      runs_with_data.append(run_numbers[idx])
  stats_tuple = get_run_stats(tset,
                              two_theta_low_set,
                              two_theta_high_set,
                              nset,
                              I_sig_I_low_set,
                              I_sig_I_high_set,
                              tuple(boundaries),
                              tuple(lengths),
                              runs_with_data,
                              ratio_cutoff=ratio_cutoff,
                              n_strong_cutoff=n_strong_cutoff)
  png = plot_run_stats(stats_tuple, d_min, run_tags=run_tags, interactive=interactive, xsize=xsize, ysize=ysize)
  return png

if __name__ == "__main__":
  import sys
  plot_multirun_stats(sys.argv[1])
