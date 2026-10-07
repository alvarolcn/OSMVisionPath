"""D-LinkNet34 architecture matching the original DeepGlobe checkpoint names.

Adapted from zlckanata/DeepGlobe-Road-Extraction-Challenge (MIT).
See THIRD_PARTY_NOTICES.md. No pretrained ResNet download is needed.
"""
import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import resnet34


class Dblock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        for i, dilation in enumerate((1, 2, 4, 8), 1):
            setattr(self, f'dilate{i}', nn.Conv2d(channels, channels, 3,
                padding=dilation, dilation=dilation))

    def forward(self, x):
        result, current = x, x
        for i in range(1, 5):
            current = F.relu(getattr(self, f'dilate{i}')(current))
            result = result + current
        return result


class DecoderBlock(nn.Module):
    def __init__(self, channels, filters):
        super().__init__()
        quarter = channels // 4
        self.conv1 = nn.Conv2d(channels, quarter, 1)
        self.norm1 = nn.BatchNorm2d(quarter)
        self.deconv2 = nn.ConvTranspose2d(quarter, quarter, 3, stride=2, padding=1, output_padding=1)
        self.norm2 = nn.BatchNorm2d(quarter)
        self.conv3 = nn.Conv2d(quarter, filters, 1)
        self.norm3 = nn.BatchNorm2d(filters)

    def forward(self, x):
        x = F.relu(self.norm1(self.conv1(x)))
        x = F.relu(self.norm2(self.deconv2(x)))
        return F.relu(self.norm3(self.conv3(x)))


class DinkNet34(nn.Module):
    def __init__(self):
        super().__init__()
        backbone = resnet34(weights=None)
        self.firstconv, self.firstbn = backbone.conv1, backbone.bn1
        self.firstrelu, self.firstmaxpool = backbone.relu, backbone.maxpool
        for i in range(1, 5):
            setattr(self, f'encoder{i}', getattr(backbone, f'layer{i}'))
        self.dblock = Dblock(512)
        for i, channels, filters in ((4,512,256),(3,256,128),(2,128,64),(1,64,64)):
            setattr(self, f'decoder{i}', DecoderBlock(channels, filters))
        self.finaldeconv1 = nn.ConvTranspose2d(64,32,4,2,1)
        self.finalconv2 = nn.Conv2d(32,32,3,padding=1)
        self.finalconv3 = nn.Conv2d(32,1,3,padding=1)

    def forward(self, x):
        x = self.firstmaxpool(self.firstrelu(self.firstbn(self.firstconv(x))))
        encoded = []
        for i in range(1, 5):
            x = getattr(self, f'encoder{i}')(x)
            encoded.append(x)
        x = self.dblock(x)
        for i in (4,3,2):
            x = getattr(self, f'decoder{i}')(x) + encoded[i-2]
        x = self.decoder1(x)
        x = F.relu(self.finaldeconv1(x))
        x = F.relu(self.finalconv2(x))
        return torch.sigmoid(self.finalconv3(x))


class GuiCompatibleDLinkNet(nn.Module):
    """Accept GUI RGB [0,1]; reproduce original BGR [-1.6,1.6] inputs."""
    def __init__(self, network):
        super().__init__()
        self.network = network

    def forward(self, rgb):
        bgr = rgb[:, [2,1,0], :, :]
        return self.network(bgr * 3.2 - 1.6)
