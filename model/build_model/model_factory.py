import tensorflow as tf

import settings
from config import opts
from utils.util_class import WrongInputException
import utils.util_funcs as uf
from model.build_model.depth_net import DepthNetBasic, DepthNetNoResize, DepthNetFromPretrained
from model.build_model.pose_net import PoseNet
from model.build_model.flow_net import PWCNet
import model.build_model.model_wrappers as mw
import model.build_model.model_utils as mu


PRETRAINED_MODELS = ["MobileNetV2", "NASNetMobile", "DenseNet121", "VGG16", "Xception", "ResNet50V2", "NASNetLarge"]
DEFAULT_SHAPE = (opts.BATCH_SIZE, opts.SNIPPET_LEN, opts.IM_HEIGHT, opts.IM_WIDTH, 3)


class ModelFactory:
    def __init__(self, input_shape=DEFAULT_SHAPE,
                 net_names=opts.NET_NAMES,
                 depth_activation=opts.DEPTH_ACTIVATION,
                 pretrained_weight=opts.PRETRAINED_WEIGHT,
                 stereo=opts.STEREO,
                 stereo_extrinsic=opts.STEREO_EXTRINSIC):
        self.input_shape = input_shape
        self.net_names = net_names
        self.activation = depth_activation
        self.pretrained_weight = pretrained_weight
        self.stereo = stereo
        self.stereo_extrinsic = stereo_extrinsic

    def get_model(self):
        models = dict()

        if "depth" in self.net_names:
            depth_activation = self.activation_factory(self.activation)
            conv_depth = self.conv2d_factory(opts.DEPTH_CONV_ARGS)
            upsample_interp_d = opts.DEPTH_UPSAMPLE_INTERP
            depthnet = self.depth_net_factory(self.net_names["depth"], conv_depth,
                                              depth_activation, upsample_interp_d)
            models["depthnet"] = depthnet

        if "camera" in self.net_names:
            conv_pose = self.conv2d_factory(opts.POSE_CONV_ARGS)
            posenet = self.pose_net_factory(self.net_names["camera"], conv_pose)
            models["posenet"] = posenet

        if "flow" in self.net_names:
            conv_flow = self.conv2d_factory(opts.FLOW_CONV_ARGS)
            flownet = self.flow_net_factory(self.net_names["flow"], conv_flow)
            models["flownet"] = flownet

        if self.stereo_extrinsic:
            model_wrapper = mw.StereoPoseModelWrapper(models)
        elif self.stereo:
            model_wrapper = mw.StereoModelWrapper(models)
        else:
            model_wrapper = mw.ModelWrapper(models)

        return model_wrapper

    def activation_factory(self, activ_name):
        if activ_name == "InverseSigmoid":
            return InverseSigmoidActivation()
        elif activ_name == "Exponential":
            return ExponentialActivation()
        else:
            WrongInputException("[activation_factory] wrong activation name: " + activ_name)

    def conv2d_factory(self, src_args):
        # convert string arguments for tf.keras.layers.Conv2D to object arguments
        dst_args = {}
        key = "activation"
        if key in src_args:
            if src_args[key] == "leaky_relu":
                dst_args[key] = tf.keras.layers.LeakyReLU(src_args[key + "_param"])
            else:
                dst_args[key] = tf.keras.layers.ReLU()

        key = "kernel_initializer"
        if key in src_args:
            if src_args[key] == "truncated_normal":
                dst_args[key] = tf.keras.initializers.TruncatedNormal(stddev=src_args[key + "_param"])
            else:
                dst_args[key] = tf.keras.initializers.GlorotUniform()

        # change default arguments of Conv2D layer
        conv_layer = mu.CustomConv2D(**dst_args)
        return conv_layer

    def depth_net_factory(self, net_name, conv2d_d, pred_activ, upsample_interp):
        if net_name == "DepthNetBasic":
            depth_net = DepthNetBasic(self.input_shape, conv2d_d, pred_activ, upsample_interp)()
        elif net_name == "DepthNetNoResize":
            depth_net = DepthNetNoResize(self.input_shape, conv2d_d, pred_activ, upsample_interp)()
        elif net_name in PRETRAINED_MODELS:
            depth_net = DepthNetFromPretrained(self.input_shape, conv2d_d, pred_activ, upsample_interp,
                                               net_name, self.pretrained_weight)()
        else:
            raise WrongInputException("[depth_net_factory] wrong depth net name: " + net_name)
        return depth_net

    def pose_net_factory(self, net_name, conv2d_p):
        if net_name == "PoseNet":
            posenet = PoseNet(self.input_shape, conv2d_p)()
        else:
            raise WrongInputException("[pose_net_factory] wrong pose net name: " + net_name)
        return posenet

    def flow_net_factory(self, net_name, conv2d_f):
        if net_name == "PWCNet":
            flownet = PWCNet(self.input_shape, conv2d_f)()
        else:
            raise WrongInputException("[flow_net_factory] wrong flow net name: " + net_name)
        return flownet


class InverseSigmoidActivation:
    def __call__(self, x):
        y = tf.math.sigmoid(x) + 0.01
        y = uf.safe_reciprocal_number(y)
        return y


class ExponentialActivation:
    def __call__(self, x):
        y = tf.math.sigmoid(x + 1.)*10. - 5.
        y = tf.exp(y)
        return y


# ==================================================
import os.path as op


def test_build_model():
    vode_model = ModelFactory(stereo=True).get_model()
    vode_model.summary()
    print("model input shapes:")
    for i, input_tensor in enumerate(vode_model.inputs()):
        print("input", i, input_tensor.name, input_tensor.get_shape())

    print("model output shapes:")
    for name, output in vode_model.outputs().items():
        if isinstance(output, list):
            for out in output:
                print(name, out.name, out.get_shape())
        else:
            print(name, output.name, output.get_shape())

    # record model architecture into text and image files
    vode_model.plot_model(op.dirname(opts.PROJECT_ROOT))
    summary_file = op.join(opts.PROJECT_ROOT, "../summary.txt")
    with open(summary_file, 'w') as fh:
        vode_model.summary(print_fn=lambda x: fh.write(x + '\n'))

    print("trainable weights", type(vode_model.trainable_weights()), len(vode_model.trainable_weights()))


if __name__ == "__main__":
    test_build_model()

