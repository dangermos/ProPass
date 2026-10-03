"""Shared classifier preprocessing, preserving full packaging aspect ratio."""
from PIL import Image, ImageOps


def padded_rgb(image, size=224):
    image = image.convert("RGB")
    return ImageOps.pad(image, (size, size), method=Image.Resampling.BILINEAR,
                        color=(114, 114, 114), centering=(0.5, 0.5))


def classifier_transform(training=False):
    from torchvision import transforms
    operations = [transforms.Lambda(padded_rgb)]
    if training:
        operations.extend([
            transforms.ColorJitter(brightness=0.18, contrast=0.18, saturation=0.12, hue=0.025),
            transforms.RandomApply([transforms.GaussianBlur(3, sigma=(0.1, 0.8))], p=0.1),
        ])
    operations.extend([transforms.ToTensor(),
                       transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    return transforms.Compose(operations)

