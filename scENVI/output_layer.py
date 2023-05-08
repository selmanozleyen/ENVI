import tensorflow as tf


class LinearLayer(tf.keras.layers.Layer):
    """
    Custom keras linear layer

    Args:
        units (int): layer output dimension
        input_dim (int): layer input dimension
        kernel_init (keras initializer): initializer for layer weights
        bias_init (keras initializer): initializer of layer biases
    """

    def __init__(self, units, input_dim, kernel_init, bias_init, name):
        super(LinearLayer, self).__init__()
        self.w = self.add_weight(
            shape=(input_dim, units),
            initializer=kernel_init,
            trainable=True,
            name=name + "/kernel",
        )
        self.b = self.add_weight(
            shape=(units,), initializer=bias_init, trainable=True, name=name + "/bias"
        )

    def call(self, inputs):
        return tf.matmul(inputs, self.w) + self.b


class ConstantLayer(tf.keras.layers.Layer):
    """
    Custom keras constant layer with biases only

    Args:
        units (int): number of neurons in the layer
        input_dim (int): layer input dimension
        bias_init (keras initializer): initializer of layer biases
        comm_disp (bool): whether the spatial and single cell distributions share
            dispersion parameters
        const_disp (bool): whether dispersion parameters are inferred per gene
            instead of per (gene, sample) pair
    """

    def __init__(self, units, input_dim, bias_init, name):
        super(ConstantLayer, self).__init__()
        self.b = self.add_weight(
            shape=(units,), initializer=bias_init, trainable=True, name=name + "/bias"
        )

    def call(self, inputs):
        return tf.tile(self.b[None, :], [inputs.shape[0], 1])


class ENVIOutputLayer(tf.keras.layers.Layer):
    """
    Custom keras layer for ENVI expression decoder output

    Predicts the parameters of the spatial and single cell distributions.
    For poisson distributions, predicts the rate.
    For negative binomial and normal distributions, predicts the rate and dispersion.
    For zero-inflated distributions, predicts the rate, dispersion and zero-inflation.

    Args:
        units (int): layer output dimension
        input_dim (int): layer input dimension
        kernel_init (keras initializer): initializer for layer weights
        bias_init (keras initializer): initializer of layer biases
        spatial_dist (str): variational distribution for spatial data
            (default pois, could be 'pois', 'nb', 'zinb', 'norm' or 'full_norm')
        sc_dist (str): variational distribution for single cell data
            (default nb, could be 'pois', 'nb', 'zinb', 'norm' or 'full_norm')
    """

    def __init__(
        self,
        input_dim,
        units,
        kernel_init,
        bias_init,
        spatial_dist="pois",
        sc_dist="nb",
        comm_disp=False,
        const_disp=False,
        name="dec_exp_output",
    ):
        super(ENVIOutputLayer, self).__init__()

        self.input_dim = input_dim
        self.units = units
        self.spatial_dist = spatial_dist
        self.sc_dist = sc_dist
        self.comm_disp = comm_disp
        self.const_disp = const_disp
        self.name = name
        self.kernel_init = kernel_init
        self.bias_init = bias_init

        # Variational distribution parameters
        self.r = LinearLayer(units, input_dim, kernel_init, bias_init, name=name + "_r")
        self.init_dispersion_layers()

    def dist_has_p(self, mode="spatial"):
        p_dists = ["zinb", "nb", "full_norm"]
        if self.comm_disp:
            return self.spatial_dist in p_dists or self.sc_dist in p_dists
        return getattr(self, mode + "_dist") in p_dists

    def dist_has_d(self, mode="spatial"):
        d_dists = ["zinb"]
        if self.comm_disp:
            return self.spatial_dist in d_dists or self.sc_dist in d_dists
        return getattr(self, mode + "_dist") in d_dists

    def init_dispersion_layers(self):
        if self.dist_has_p("spatial"):
            self.p_spatial = self.init_layer(name="_p_spatial")
            if self.comm_disp:
                self.p_sc = self.p_spatial
        if self.dist_has_d("spatial"):
            self.d_spatial = self.init_layer(name="_d_spatial")
            if self.comm_disp:
                self.d_sc = self.d_spatial

        if not self.comm_disp:
            if self.dist_has_p("sc"):
                self.p_sc = self.init_layer(name="_p_sc")
            if self.dist_has_d("sc"):
                self.d_sc = self.init_layer(name="_d_sc")

    def init_layer(self, name):
        if self.const_disp:
            return ConstantLayer(
                self.units, self.input_dim, self.bias_init, name=self.name + name
            )
        return LinearLayer(
            self.units,
            self.input_dim,
            self.kernel_init,
            self.bias_init,
            name=self.name + name,
        )

    def call(self, inputs, mode="spatial"):
        r = self.r(inputs)

        if getattr(self, mode + "_dist") == "zinb":
            p = getattr(self, "p_" + mode)(inputs)
            d = getattr(self, "d_" + mode)(inputs)
            return (r, p, d)

        if getattr(self, mode + "_dist") in ["nb", "full_norm"]:
            p = getattr(self, "p_" + mode)(inputs)
            return (r, p)

        return r
