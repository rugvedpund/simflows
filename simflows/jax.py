##--------------------------------------------------------------------##
# %%

import jax

jax.config.update("jax_enable_x64", True)

# %%

##--------------------------------------------------------------------##
# %%


def random_normal(shape, seed=42, mean=0, sigma=1):
    key = jax.random.PRNGKey(seed)
    return jax.random.normal(key, shape) * sigma + mean


# %%