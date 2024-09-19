# %%

from simflows.imports import *

# %%


def make_toysim(motherseed: int = 42):
    rng = np.random.RandomState(motherseed)
    seed1, seed2 = rng.randint(0, 1000, 2)
    ntimes = 650
    idxs = simjax.random_normal((ntimes, 1), seed=seed1, mean=2.5, sigma=0.5)
    amp20MHz = simjax.random_normal((ntimes, 1), seed=seed2, mean=1e4, sigma=1e4)
    amp20MHz = jnp.abs(amp20MHz)
    sim = simloader.make_mock_sim(ntimes=ntimes, idxs=idxs, amp20MHz=amp20MHz, da_amp=1)
    return sim


def sim_to_jax(sim):
    fg, da, cmb, _, delta = sim
    jfg, jda, jcmb, jdelta = (
        jnp.array(fg),
        jnp.array(da),
        jnp.array(cmb),
        jnp.array(delta),
    )
    return jfg, jda, jcmb, jdelta


def doPCA(sim):
    delta, fg, da, cmb = sim.sel(kind=["delta", "fg", "da", "cmb"])
    delta_pca = simpca.get_pca(delta, "times", "freqs", other_dims=[])
    proj = simpca.get_pca_proj(
        fg, delta, da, cmb, delta_pca, "times", "freqs", other_dims=[]
    )
    return delta_pca, proj


def make_random_weights(motherseed: int = 42):
    rng = np.random.RandomState(motherseed)
    seed1, seed2 = rng.randint(0, 1000, 2)
    wda = make_w(seed1)
    wcmb = make_w(seed2)
    return wda, wcmb


def make_w(seed: int = 42):
    key = jax.random.PRNGKey(seed)
    w = jax.random.uniform(key, shape=(50)) - 0.5
    w = w / jnp.linalg.norm(w)
    wsigns = jnp.sign(w)
    w = w / wsigns[-1]  # enforce positive sign for first element
    return w


def optimize(loss, wtensor, deltafg, signal, niter=10000):
    learning_rate = 0.01
    optimizer = optax.chain(
        optax.clip_by_global_norm(1.0),
        optax.adam(
            optax.exponential_decay(
                init_value=learning_rate,
                transition_steps=niter / 1,
                decay_rate=0.99,
            )
        ),
    )
    opt_state = optimizer.init(wtensor)

    @jax.jit
    def _step(w, _opt_state):
        loss_value, grads = jax.value_and_grad(loss)(w, deltafg, signal)
        updates, _opt_state = optimizer.update(grads, _opt_state)
        w = optax.apply_updates(w, updates)
        return w, _opt_state, loss_value

    iterations = np.zeros((niter))
    loss_vals = np.zeros((niter))
    wnorms = np.zeros((niter))
    witers = np.zeros((niter, 50))

    for i in tqdm(range(niter), leave=False, desc="Optimizer"):
        witers[i] = wtensor
        wnorms[i] = jnp.linalg.norm(wtensor)
        wtensor, opt_state, loss_value = _step(wtensor, opt_state)
        iterations[i], loss_vals[i] = i, loss_value
    woptim = wtensor
    return woptim, iterations, loss_vals, wnorms, witers


def lossfn(w, deltafg, signal):
    wnorm = jnp.linalg.norm(w)  # frobenius norm sqrt(sum(w**2))
    w = w / wnorm
    deltafg_tilde = jnp.einsum("f,tf->t", w, deltafg)
    signal_tilde = jnp.einsum("f,tf->t", w, signal)
    signal_tilde = signal_tilde.mean()
    return (jnp.var(deltafg_tilde) / signal_tilde**2) + (wnorm**2 - 1) ** 2


def optimize_wtensors(motherseed, niter=1000):
    sim = make_toysim(motherseed)
    _, jda, jcmb, jdelta = sim_to_jax(sim)
    wda, wcmb = make_random_weights(motherseed)
    woptim_da, iter_da, loss_vals_da, wnorms_da, witers_da = optimize(
        lossfn, wda, jdelta, jda, niter
    )
    woptim_cmb, iter_cmb, loss_vals_cmb, wnorms_cmb, witers_cmb = optimize(
        lossfn, wcmb, jdelta, jcmb, niter
    )

    iterations = xr.DataArray(iter_da, dims=("iter"))
    freqs = xr.DataArray(sim.freqs, dims=("freqs"))
    wda = xr.Dataset(
        {
            "woptim": xr.DataArray(woptim_da, dims=("freqs")),
            "loss": xr.DataArray(loss_vals_da, dims=("iter")),
            "wnorm": xr.DataArray(wnorms_da, dims=("iter")),
            "witer": xr.DataArray(witers_da, dims=("iter", "freqs")),
        },
        coords={"freqs": freqs, "iter": iterations},
    )
    wcmb = xr.Dataset(
        {
            "woptim": xr.DataArray(woptim_cmb, dims=("freqs")),
            "loss": xr.DataArray(loss_vals_cmb, dims=("iter")),
            "wnorm": xr.DataArray(wnorms_cmb, dims=("iter")),
            "witer": xr.DataArray(witers_cmb, dims=("iter", "freqs")),
        },
        coords={"freqs": freqs, "iter": iterations},
    )
    return wda, wcmb


def optimize_proj_wtensors(motherseed, niter=1000):
    sim = make_toysim(motherseed)
    delta_pca, proj = doPCA(sim)
    wda, wcmb = make_random_weights(motherseed)
    jpdelta, jpda, jpcmb = map(
        jnp.array,
        [
            proj.sel(kind="pdelta").data,
            proj.sel(kind="pda").data,
            proj.sel(kind="pcmb").data,
        ],
    )
    woptim_da, iter_da, loss_vals_da, wnorms_da, witers_da = optimize(
        lossfn, wda, jpdelta, jpda, niter
    )
    woptim_cmb, iter_cmb, loss_vals_cmb, wnorms_cmb, witers_cmb = optimize(
        lossfn, wcmb, jpdelta, jpcmb, niter
    )

    iterations = xr.DataArray(iter_da, dims=("iter"))
    freqs_eig = xr.DataArray(proj.freqs_eig, dims=("freqs_eig"))
    wda = xr.Dataset(
        {
            "woptim": xr.DataArray(woptim_da, dims=("freqs_eig")),
            "loss": xr.DataArray(loss_vals_da, dims=("iter")),
            "wnorm": xr.DataArray(wnorms_da, dims=("iter")),
            "witer": xr.DataArray(witers_da, dims=("iter", "freqs_eig")),
        },
        coords={"freqs_eig": freqs_eig, "iter": iterations},
    )
    wcmb = xr.Dataset(
        {
            "woptim": xr.DataArray(woptim_cmb, dims=("freqs_eig")),
            "loss": xr.DataArray(loss_vals_cmb, dims=("iter")),
            "wnorm": xr.DataArray(wnorms_cmb, dims=("iter")),
            "witer": xr.DataArray(witers_cmb, dims=("iter", "freqs_eig")),
        },
        coords={"freqs_eig": freqs_eig, "iter": iterations},
    )
    return wda, wcmb


def run_seeds(seeds, niter=1000):
    results = dict()
    for seed in seeds:
        wda, wcmb = optimize_wtensors(seed, niter)
        wpda, wpcmb = optimize_proj_wtensors(seed, niter)
        results[seed] = (wda, wcmb, wpda, wpcmb)
    return results


# %%

niter = 100000
seed = 0
sim = make_toysim()
jfg, jpda, jpcmb, jpdelta = sim_to_jax(sim)
delta_pca, proj = doPCA(sim)
wda0, wcmb0 = make_random_weights(seed)
wda, wcmb = optimize_wtensors(seed, niter)
wpda, wpcmb = optimize_proj_wtensors(seed, niter)

# %%

fig, ax = plt.subplots(1, 3, figsize=(15, 4))
wpda.loss.plot(label="da", ax=ax[0], yscale="log")
wpcmb.loss.plot(label="cmb", ax=ax[0])
wpda.wnorm.plot(label="da", ax=ax[1])
wpcmb.wnorm.plot(label="cmb", ax=ax[1])
wpda.woptim.plot(label="da", ax=ax[2])
wpcmb.woptim.plot(label="cmb", ax=ax[2])
plt.legend()
plt.show()


# %%

plt.plot(xr.dot(wpda.woptim, delta_pca.U, dims="freqs_eig"), label="da")
plt.plot(xr.dot(wpcmb.woptim, delta_pca.U, dims="freqs_eig"), label="cmb")
wda.woptim.plot(color="C0", ls="--", alpha=0.7)
wcmb.woptim.plot(color="C1", ls="--", alpha=0.7)
plt.plot([], [], color="k", ls="--", label="w/o pca")
plt.legend()
plt.show()


# %%


# %%

pca_loss_da = proj.sel(kind="pdelta").var("times") / proj.sel(kind="mean pda") ** 2
pca_loss_cmb = proj.sel(kind="pdelta").var("times") / proj.sel(kind="mean pcmb") ** 2
wpda_loss = wpda.loss.isel(iter=slice(-1000, None)).mean("iter")
wpcmb_loss = wpcmb.loss.isel(iter=slice(-1000, None)).mean("iter")

pca_loss_da.plot.scatter(label="da", yscale="log")
pca_loss_cmb.plot.scatter(label="cmb", yscale="log")
plt.axhline(wpda_loss, color="C0", label="wpda")
plt.axhline(wpcmb_loss, color="C1", label="wpcmb")
plt.legend()
plt.title("pca vs jax loss")
plt.show()


# %%

wpda_loss = wpda.loss.isel(iter=slice(-1000, None)).mean("iter")
wpcmb_loss = wpcmb.loss.isel(iter=slice(-1000, None)).mean("iter")
plt.show()

# %%
