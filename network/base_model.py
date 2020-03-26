"""
This file defines the abstract model for all the models in this repo
This is suppose to be the parent class for all the other models
"""


# Built-in

# Libs
from tqdm import tqdm

# PyTorch
import torch
from torch import nn
from torch.autograd import Variable

# Own modules
from mrs_utils import vis_utils
from network import network_utils


class Base(nn.Module):
    def __init__(self):
        self.lbl_margin = 0
        super(Base, self).__init__()

    def forward(self, *inputs_):
        """
        Forward operation in network training
        This does not necessarily equals to the inference, i.e., less output in inference
        :param inputs_:
        :return:
        """
        raise NotImplementedError

    def inference(self, *inputs_):
        outputs = self.forward(*inputs_)
        if isinstance(outputs, tuple):
            return outputs[0]
        else:
            return outputs

    def init_weight(self):
        """
        Initialize weights of the model
        :return:
        """
        for m in network_utils.iterate_sublayers(self):
            if isinstance(m, nn.Conv2d):
                torch.nn.init.xavier_uniform(m.weight)
                torch.nn.init.xavier_uniform(m.bias)

    def set_train_params(self, learn_rate, **kwargs):
        """
        Set training parameters with proper weights
        :param learn_rate:
        :param kwargs:
        :return:
        """
        return [
            {'params': self.encoder.parameters(), 'lr': learn_rate[0]},
            {'params': self.decoder.parameters(), 'lr': learn_rate[1]}
        ]

    def step(self, data_loader, device, optm, phase, criterions, bp_loss_idx=0, save_image=True,
             mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225), loss_weights=None):
        """
        This function does one forward and backward path in the training
        Print necessary message
        :param kwargs:
        :return:
        """
        if isinstance(bp_loss_idx, int):
            bp_loss_idx = (bp_loss_idx,)
        if loss_weights is None:
            loss_weights = {a: 1.0 for a in bp_loss_idx}
        else:
            assert len(loss_weights) == len(bp_loss_idx)
            loss_weights = [a/sum(loss_weights) for a in loss_weights]
            loss_weights = {a: b for (a, b) in zip(bp_loss_idx, loss_weights)}

        loss_dict = {}
        for img_cnt, (image, label) in enumerate(tqdm(data_loader, desc='{}'.format(phase))):
            image = Variable(image, requires_grad=True).to(device)
            label = Variable(label).long().to(device)
            optm.zero_grad()

            # forward step
            if phase == 'train':
                pred = self.forward(image)
            else:
                with torch.autograd.no_grad():
                    pred = self.forward(image)

            # loss
            # crop margin if necessary & reduce channel dimension
            if self.lbl_margin > 0:
                label = label[:, self.lbl_margin:-self.lbl_margin, self.lbl_margin:-self.lbl_margin]
            loss_all = 0
            for c_cnt, c in enumerate(criterions):
                loss = c(pred, label)
                if phase == 'train' and c_cnt in bp_loss_idx:
                    loss_all += loss_weights[c_cnt] * loss
                c.update(loss, image.size(0))
            if phase == 'train':
                loss_all.backward()
                optm.step()

            if save_image and img_cnt == 0:
                img_image = image.detach().cpu().numpy()
                if self.lbl_margin > 0:
                    img_image = img_image[:, :, self.lbl_margin: -self.lbl_margin, self.lbl_margin: -self.lbl_margin]
                lbl_image = label.cpu().numpy()
                pred_image = pred.detach().cpu().numpy()
                banner = vis_utils.make_tb_image(img_image, lbl_image, pred_image, self.n_class, mean, std)
                loss_dict['image'] = torch.from_numpy(banner)
        for c in criterions:
            loss_dict[c.name] = c.get_loss()
            c.reset()
        return loss_dict

    def step_aux(self, data_loader, device, optm, phase, criterions, cls_criterion, cls_weight, bp_loss_idx=0,
                 save_image=True, mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225), loss_weights=None):
        """
        This function does one forward and backward path in the training
        Print necessary message
        :param kwargs:
        :return:
        """
        if isinstance(bp_loss_idx, int):
            bp_loss_idx = (bp_loss_idx,)
        if loss_weights is None:
            loss_weights = {a: 1.0 for a in bp_loss_idx}
        else:
            assert len(loss_weights) == len(bp_loss_idx)
            loss_weights = [a/sum(loss_weights) for a in loss_weights]
            loss_weights = {a: b for (a, b) in zip(bp_loss_idx, loss_weights)}

        loss_dict = {}
        for img_cnt, (image, label, cls) in enumerate(tqdm(data_loader, desc='{}'.format(phase))):
            image = Variable(image, requires_grad=True).to(device)
            label = Variable(label).long().to(device)
            cls = Variable(cls).to(device)
            optm.zero_grad()

            # forward step
            if phase == 'train':
                pred, cls_hat = self.forward(image)
            else:
                with torch.autograd.no_grad():
                    pred, cls_hat = self.forward(image)

            # loss
            # crop margin if necessary & reduce channel dimension
            if self.lbl_margin > 0:
                label = label[:, self.lbl_margin:-self.lbl_margin, self.lbl_margin:-self.lbl_margin]
            loss_all = 0
            for c_cnt, c in enumerate(criterions):
                loss = c(pred, label)
                if phase == 'train' and c_cnt in bp_loss_idx:
                    loss_all += loss_weights[c_cnt] * loss
                c.update(loss, image.size(0))
            loss = cls_criterion(cls_hat, cls)
            loss_all += cls_weight * loss
            cls_criterion.update(loss, image.size(0))
            if phase == 'train':
                loss_all.backward()
                optm.step()

            if save_image and img_cnt == 0:
                img_image = image.detach().cpu().numpy()
                if self.lbl_margin > 0:
                    img_image = img_image[:, :, self.lbl_margin: -self.lbl_margin, self.lbl_margin: -self.lbl_margin]
                lbl_image = label.cpu().numpy()
                pred_image = pred.detach().cpu().numpy()
                banner = vis_utils.make_tb_image(img_image, lbl_image, pred_image, self.n_class, mean, std)
                loss_dict['image'] = torch.from_numpy(banner)
        for c in criterions:
            loss_dict[c.name] = c.get_loss()
            c.reset()
        loss_dict[cls_criterion.name] = cls_criterion.get_loss()
        cls_criterion.reset()
        return loss_dict

    def step_mixed_batch(self, data_loader_ref, data_loader_others, device, optm, phase, criterions, bp_loss_idx=0,
                         save_image=True, mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225), loss_weights=None):
        """
        This function does one forward and backward path in the training
        Print necessary message
        :param kwargs:
        :return:
        """
        def infi_loop(dl):
            while True:
                for x in dl: yield x

        for cnt, dlo in enumerate(data_loader_others):
            data_loader_others[cnt] = infi_loop(dlo)

        # settings
        if isinstance(bp_loss_idx, int):
            bp_loss_idx = (bp_loss_idx,)
        if loss_weights is None:
            loss_weights = {a: 1.0 for a in bp_loss_idx}
        else:
            assert len(loss_weights) == len(bp_loss_idx)
            loss_weights = [a/sum(loss_weights) for a in loss_weights]
            loss_weights = {a: b for (a, b) in zip(bp_loss_idx, loss_weights)}

        loss_dict = {}
        for img_cnt, (image, label) in enumerate(tqdm(data_loader_ref, desc='{}'.format(phase))):
            # load data
            if phase == 'train':
                for dlo in data_loader_others:
                    image_other, label_other = next(dlo)
                    image = torch.cat([image, image_other], dim=0)
                    label = torch.cat([label, label_other], dim=0)
            image = Variable(image, requires_grad=True).to(device)
            label = Variable(label).long().to(device)

            optm.zero_grad()

            # forward step
            if phase == 'train':
                pred = self.forward(image)
            else:
                with torch.autograd.no_grad():
                    pred = self.forward(image)

            # loss
            if self.lbl_margin > 0:
                label = label[:, self.lbl_margin:-self.lbl_margin, self.lbl_margin:-self.lbl_margin]
            loss_all = 0
            for c_cnt, c in enumerate(criterions):
                loss = c(pred, label)
                if phase == 'train' and c_cnt in bp_loss_idx:
                    loss_all += loss_weights[c_cnt] * loss
                c.update(loss, image.size(0))
            if phase == 'train':
                loss_all.backward()
                optm.step()

            if save_image and img_cnt == 0:
                img_image = image.detach().cpu().numpy()
                if self.lbl_margin > 0:
                    img_image = img_image[:, :, self.lbl_margin: -self.lbl_margin, self.lbl_margin: -self.lbl_margin]
                lbl_image = label.cpu().numpy()
                pred_image = pred.detach().cpu().numpy()
                banner = vis_utils.make_tb_image(img_image, lbl_image, pred_image, self.n_class, mean, std)
                loss_dict['image'] = torch.from_numpy(banner)
        for c in criterions:
            loss_dict[c.name] = c.get_loss()
            c.reset()
        return loss_dict


if __name__ == '__main__':
    pass
