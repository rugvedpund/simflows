import lusee
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import argparse
import seaborn as sns
import pandas as pd


def timeit(func):
    import time

    def wrapper(*args, **kwargs):
        start = time.time()
        out = func(*args, **kwargs)
        print(f"{func.__name__} took {(time.time() - start):.1f} seconds")
        return out

    return wrapper


def exp(arr: np.ndarray):
    return np.exp(arr - arr.max())


def is_comb(comb):
    assert comb[-1] in ["R", "I"]
    assert len(comb) == 3
    return True


def get_configname(config):
    pass


def flatten_combs(data):
    ntimes, ncombs, nfreqs = data.shape  # (ntimes, ncombs, nfreqs)
    data = np.transpose(data, (1, 0, 2))  # (ncombs, ntimes, nfreqs)
    data = data.reshape(ncombs * ntimes, nfreqs)  # (ncombs*ntimes, nfreqs)
    data = data.T  # (nfreqs, ncombs*ntimes)
    return data


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="*", help="config yaml paths")
    parser.add_argument("--outputs", nargs="*", help="output dir path")
    parser.add_argument("--params_yaml", type=str, help="param yaml path")
    parser.add_argument("--retrain", action="store_true")
    parser.add_argument("--comb", type=str, help="e.g. 00R, auto, all", default="00R")
    return parser


def combs(nbeams=4):
    if nbeams != 4:
        raise NotImplementedError
    return [
        "00R",
        "01R",
        "01I",
        "02R",
        "02I",
        "03R",
        "03I",
        "11R",
        "12R",
        "12I",
        "13R",
        "13I",
        "22R",
        "23R",
        "23I",
        "33R",
    ]


def all_combs(n):
    combs = []
    for i in range(n):
        for j in range(n):
            if i == j:
                combs.append(f"{i}{j}R")
            if i > j:
                combs.append(f"{j}{i}R")
            if i < j:
                combs.append(f"{i}{j}I")
    return combs

def get_combs_list(comb):
    if comb == "auto":
        return ["00R","11R","22R","33R"]
    if comb == "all":
        return combs(4)
    if comb == "crossimag":
        return ["01I","02I","03I","12I","13I","23I"]
    if comb == "crossreal":
        return ["01R","02R","03R","12R","13R","23R"]
    if is_comb(comb):
        return [comb]
    raise ValueError(f"comb {comb} is not valid")

def plt_waterfall(D, comb, ax=None, **kwargs):
    if ax is None:
        ax = plt.gca()
    im = ax.imshow(
        D[:, comb, :].T,
        aspect="auto",
        # extent=(D.freq[0], D.freq[-1], len(D.times), 0),
        origin="lower",
        cmap="viridis",
        **kwargs,
    )
    cbar = plt.colorbar(im, ax=ax, shrink=0.5)
    cbar.ax.tick_params(labelsize=8)
    ax.set_ylabel("f(MHz)")
    ax.set_xlabel("time")
    ax.set_title(f"{comb}")
    return ax


def plt_scree(sky, ax=None, scale_rms=1.0, true_amp=1.0, **kwargs):
    if ax is None:
        ax = plt.gca()
    ax.plot(np.abs(sky.ulsa.proj_mean), c="C0", **kwargs)
    ax.plot(np.abs(sky.da.proj_mean * true_amp), c="C1", **kwargs)
    ax.plot(np.abs(sky.cmb.proj_mean * true_amp), c="C2", **kwargs)
    ax.plot(sky.ulsa.proj_rms * scale_rms, c="C3", **kwargs)
    ax.set_xlabel("eigmodes")
    ax.set_ylabel("T[K]")
    ax.set_yscale("log")
    ax.grid()
    return ax


def plt_pairplot(data, eigmodes):
    ndim, ndata = data.shape
    nmodes = len(eigmodes)
    fig, ax = plt.subplots(nmodes, nmodes, figsize=(nmodes * 2, nmodes * 2))
    for i in range(nmodes):
        for j in range(nmodes):
            if i == j:
                ax[i, i].hist(data[eigmodes[i]])
                ax[i, i].set_xlabel(f"mode {eigmodes[i]}")
            if i < j:
                ax[i, j].set_axis_off()
            if i > j:
                ax[i, j].scatter(data[eigmodes[j]], data[eigmodes[i]])
                ax[i, j].set_xlabel(f"mode {eigmodes[j]}")
                ax[i, j].set_ylabel(f"mode {eigmodes[i]}")
    return fig, ax


def simflow_forward(simflow):
    nf_pdata = simflow.flow.forward(simflow.sky.ulsa.norm_pdata.T)
    nf_pmean = simflow.flow.forward(simflow.sky.ulsa.norm_pmean.reshape(1, -1))
    nf_pda = simflow.flow.forward(simflow.sky.da.norm_pmean.reshape(1, -1))
    nf_pcmb = simflow.flow.forward(simflow.sky.cmb.norm_pmean.reshape(1, -1))
    return nf_pdata, nf_pmean, nf_pda, nf_pcmb


def sns_pairplot(
    eigmodes,
    sky=None,
    norm_pdata=None,
    ulsa_norm_pmean=None,
    da_norm_pmean=None,
    cmb_norm_pmean=None,
):
    if sky is not None:
        norm_pdata = sky.ulsa.norm_pdata
        ulsa_norm_pmean = sky.ulsa.norm_pmean
        da_norm_pmean = sky.da.norm_pmean
        cmb_norm_pmean = sky.cmb.norm_pmean
    ndim, ndata = norm_pdata.shape
    d = np.vstack(
        [
            norm_pdata.T,
            ulsa_norm_pmean,
            da_norm_pmean,
            cmb_norm_pmean,
        ]
    )
    index = ["data"] * ndata + ["mean ulsa", "mean da", "mean cmb"]
    df = pd.DataFrame(d, index=index).reset_index()
    kwargs = {
        "markers": [".", "d", "^", "v"],
        "height": 2,
        "vars": eigmodes,
        "hue": "index",
        "diag_kind": "hist",
    }
    pairplt = sns.pairplot(df, **kwargs)
    return pairplt


def sns_pairplot_addGauss(pairplt, gauss, eigmodes, **kwargs):
    label = kwargs.get("label", None)
    color = kwargs.get("color", "C4")
    for yidx, ymode in enumerate(eigmodes):
        for xidx, xmode in enumerate(eigmodes):
            if xidx != yidx:
                ell = mpl.patches.Ellipse(
                    xy=(0, 0),
                    width=2 * gauss.sigmas[xmode],
                    height=2 * gauss.sigmas[ymode],
                    # angle=np.rad2deg(np.arccos(eve[0, 0])),
                )
                ell.set_facecolor("none")
                ell.set_edgecolor(color)
                ell.set_label(label)
                pairplt.axes[yidx, xidx].add_artist(ell)
            else:
                rms = gauss.sigmas[ymode]
                pairplt.axes[yidx, yidx].axvline(rms, color=color, label=label)
                pairplt.axes[yidx, yidx].axvline(-rms, color=color, label=label)
    return pairplt

    # for ax in pairplt.axes.flatten():
    #     xlabel = ax.get_xlabel()
    #     ylabel = ax.get_ylabel()
    #     if xlabel != '' and ylabel != '':
    #         xidx,yidx = int(xlabel), int(ylabel)
    #         ell = mpl.patches.Ellipse(xy=(0,0),
    #                                   width=2*gauss.sigmas[xidx], height=2*gauss.sigmas[yidx],
    #                                   # angle=np.rad2deg(np.arccos(eve[0, 0])),
    #                                   )
    #         ell.set_facecolor('none')
    #         ell.set_edgecolor(color)
    #         ell.set_label(label)
    #         ax.add_artist(ell)
    #         # ax.set_xlim(gauss.mu[xidx]-2*eva[0], gauss.mu[xidx]+2*eva[0])
    #         # ax.set_ylim(gauss.mu[yidx]-2*eva[1], gauss.mu[yidx]+2*eva[1])
    #     if xlabel == '' and ylabel != '':
    #         yidx = int(ylabel)
    #         rms = gauss.sigmas[yidx]
    #         ax.axvline(rms, color=color, label=label)
    #         ax.axvline(-rms, color=color, label=label)
    #         # ax.set_xlim(gauss.mu[yidx]-2*rms, gauss.mu[yidx]+2*rms)
    #     if xlabel != '' and ylabel == '':
    #         xidx = int(xlabel)
    #         rms = gauss.sigmas[xidx]
    #         ax.axvline(rms, color=color, label=label)
    #         ax.axvline(-rms, color=color, label=label)
    #         # ax.set_xlim(gauss.mu[xidx]-2*rms, gauss.mu[xidx]+2*rms)
    return pairplt


def sns_pairplot_addVectors(
    pairplt, ulsa_norm_pmean, sig_norm_pmean, eigmodes, **kwargs
):
    label = kwargs.get("label", None)
    color = kwargs.get("color", "k")
    amp = np.linspace(0,1000,num=100)
    base = ulsa_norm_pmean + sig_norm_pmean
    a0 = np.linalg.norm(sig_norm_pmean)
    unit_sig = sig_norm_pmean / a0
    vec = base[:,None] - unit_sig[:,None] * amp[None,:]
    for yidx, ymode in enumerate(eigmodes):
        for xidx, xmode in enumerate(eigmodes):
            if xidx != yidx:
                ax = pairplt.axes[yidx, xidx]
                xlim,ylim = ax.get_xlim(), ax.get_ylim()
                ax.plot(base[xmode], base[ymode], "o", color=color, label=label)
                ax.plot(vec[xmode], vec[ymode], color=color, label=label)
                ax.plot(ulsa_norm_pmean[xmode], ulsa_norm_pmean[ymode], "d", color="C1", label="mean ulsa")
                ax.set_xlim(xlim)
                ax.set_ylim(ylim)
    return pairplt


# D = lusee.Data("gaussbeam.fits")
# fig, ax = plt.subplots(4, 4, figsize=(15, 8))
# for comb, ax in zip(all_combs(4), ax.flatten()):
#     plt_waterfall(D, comb, ax=ax, norm=mcolors.SymLogNorm(linthresh=1e2))
# fig.suptitle(r"NSEW Gaussian $10^\circ$ Beams at $40^\circ$ declination")
# fig.tight_layout()
# plt.show()

# D = lusee.Data("realistic_example.fits")
# fig, ax = plt.subplots(4, 4, figsize=(15, 8))
# for comb, ax in zip(all_combs(4), ax.flatten()):
#     plt_waterfall(D, comb, ax=ax, norm=mcolors.SymLogNorm(linthresh=1e2))
# fig.suptitle("NSEW LuSEE Beams")
# fig.tight_layout()
# plt.show()

# D = lusee.Data("smallgaussbeam.fits")
# fig, ax = plt.subplots(4, 4, figsize=(15, 8))
# for comb, ax in zip(all_combs(4), ax.flatten()):
#     plt_waterfall(D, comb, ax=ax, norm=mcolors.SymLogNorm(linthresh=1e2))
# fig.suptitle(r"NSEW Gaussian $2^\circ$ Beams at $40^\circ$ declination")
# fig.tight_layout()
# plt.show()
