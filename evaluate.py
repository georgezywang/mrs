"""

"""


# Built-in
import os
import sys
sys.path.append('/home/wh145/mrs/')

# Libs
import albumentations as A
from albumentations.pytorch import ToTensor

# Own modules
from mrs_utils import misc_utils
from network import network_io, network_utils


# Settings
GPU = 0
MODEL_DIR = r'/home/wh145/models/ecvgg16_dcunet_dsmass_roads_lre1e-03_lrd1e-03_ep20_bs5_ds2_dr0p1/'
LOAD_EPOCH = 19
DATA_DIR = r'/home/wh145/processed_mass_roads'
PATCHS_SIZE = (512, 512)


def main():
    device, _ = misc_utils.set_gpu(GPU)

    # init model
    args = network_io.load_config(MODEL_DIR)
    model = network_io.create_model(args)
    if LOAD_EPOCH:
        args['trainer']['epochs'] = LOAD_EPOCH
    ckpt_dir = os.path.join(MODEL_DIR, 'epoch-{}.pth.tar'.format(args['trainer']['epochs']))
    network_utils.load(model, ckpt_dir, disable_parallel=True)
    print('Loaded from {}'.format(ckpt_dir))
    model.to(device)
    model.eval()

    # eval on dataset
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)
    tsfm_valid = A.Compose([
        A.Normalize(mean=mean, std=std),
        ToTensor(sigmoid=False),
    ])
    save_dir = os.path.join(r'/home/wh145/results/mrs/mass_roads', os.path.basename(network_utils.unique_model_name(args)))
    evaluator = network_utils.Evaluator('mass_roads', DATA_DIR, tsfm_valid, device)
    evaluator.evaluate(model, PATCHS_SIZE, 2*model.lbl_margin,
                       pred_dir=save_dir, report_dir=save_dir)


if __name__ == '__main__':
    main()
