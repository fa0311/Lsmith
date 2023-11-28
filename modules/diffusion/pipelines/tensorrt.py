import gc
import os
from typing import *
from typing import Optional

import tensorrt as trt
import torch
from diffusers import AutoencoderKL, DDPMScheduler
from diffusers.utils import randn_tensor
from PIL import Image
from polygraphy import cuda
from transformers import CLIPTextModel, CLIPTokenizer

from api.models.diffusion import ImageGenerationOptions
from lib.tensorrt.engine import (
    AutoencoderKLEngine,
    CLIPTextModelEngine,
    UNet2DConditionModelEngine,
)
from lib.tensorrt.models import BaseModel
from lib.tensorrt.utilities import TRT_LOGGER, create_models

from ..utils import convert_checkpoint_to_pipe
from .diffusers import DiffusersPipeline


class TensorRTStableDiffusionPipeline(DiffusersPipeline):
    __mode__ = "tensorrt"

    @classmethod
    def from_pretrained(
        cls,
        model_id: str,
        engine_dir: str,
        use_auth_token: Optional[str],
        device: Union[str, torch.device],
        max_batch_size: int = 1,
        hf_cache_dir: Optional[str] = None,
        full_acceleration: bool = False,
    ):
        temporary_pipe = convert_checkpoint_to_pipe(model_id)

        tokenizer = (
            CLIPTokenizer.from_pretrained(
                model_id,
                subfolder="tokenizer",
                use_auth_token=use_auth_token,
                cache_dir=hf_cache_dir,
            )
            if temporary_pipe is None
            else temporary_pipe.tokenizer
        )
        scheduler = (
            DDPMScheduler.from_pretrained(
                model_id,
                subfolder="scheduler",
                use_auth_token=use_auth_token,
                cache_dir=hf_cache_dir,
            )
            if temporary_pipe is None
            else temporary_pipe.scheduler
        )

        if full_acceleration:
            clip = CLIPTextModelEngine(model_path("clip"), stream)
            vae = AutoencoderKLEngine(model_path("vae"), stream)
            embedding_dim = 768
        else:
            clip = (
                CLIPTextModel.from_pretrained(
                    model_id,
                    subfolder="text_encoder",
                    use_auth_token=use_auth_token,
                    cache_dir=hf_cache_dir,
                )
                if temporary_pipe is None
                else temporary_pipe.text_encoder
            )
            vae = (
                AutoencoderKL.from_pretrained(
                    model_id,
                    subfolder="vae",
                    use_auth_token=use_auth_token,
                    cache_dir=hf_cache_dir,
                )
                if temporary_pipe is None
                else temporary_pipe.vae
            )
            embedding_dim = clip.config.hidden_size

        del temporary_pipe
        gc.collect()
        torch.cuda.empty_cache()

        models = create_models(
            model_id=model_id,
            use_auth_token=use_auth_token,
            device=device,
            max_batch_size=max_batch_size,
            embedding_dim=embedding_dim,
        )

        def model_path(model_name):
            return os.path.join(engine_dir, model_name + ".plan")

        stream = cuda.Stream()
        unet = UNet2DConditionModelEngine(model_path("unet"), stream)
        pipe = cls(
            id=model_id,
            models=models,
            stream=stream,
            unet=unet,
            text_encoder=clip,
            vae=vae,
            tokenizer=tokenizer,
            scheduler=scheduler,
            full_acceleration=full_acceleration,
        ).to(device=device)
        return pipe

    def __init__(
        self,
        id: str,
        models: Dict[str, BaseModel],
        stream: cuda.Stream,
        vae: AutoencoderKLEngine,
        text_encoder: CLIPTextModelEngine,
        unet: UNet2DConditionModelEngine,
        tokenizer: CLIPTokenizer,
        scheduler: DDPMScheduler,
        full_acceleration: bool = False,
    ):
        self.unet: Optional[UNet2DConditionModelEngine] = None
        self.vae: Optional[AutoencoderKLEngine] = None
        self.text_encoder: Optional[CLIPTextModelEngine] = None
        self.scheduler: Optional[DDPMScheduler] = None
        super().__init__(
            id,
            vae,
            text_encoder,
            tokenizer,
            unet,
            scheduler,
        )
        self.trt_models = models
        self.stream = stream
        self.full_acceleration = full_acceleration

    def __del__(self):
        self.stream.free()
        del self.stream

    def enterers(self):
        return [torch.inference_mode(), torch.autocast("cuda"), trt.Runtime(TRT_LOGGER)]

    def load_resources(
        self,
        opts: ImageGenerationOptions,
    ):
        super().load_resources(opts)
        image_height, image_width, batch_size = opts.height, opts.width, opts.batch_size
        if opts.multidiffusion.enable:
            tile_size = opts.multidiffusion.window_size * 8
            image_height, image_width = tile_size, tile_size
            batch_size = opts.multidiffusion.views_batch_size
        self.unet.allocate_buffers(
            shape_dict=self.trt_models["unet"].get_shape_dict(
                batch_size, image_height, image_width
            ),
            device=self.device,
        )
        if self.full_acceleration:
            self.text_encoder.allocate_buffers(
                shape_dict=self.trt_models["clip"].get_shape_dict(
                    batch_size, image_height, image_width
                ),
                device=self.device,
            )
            self.vae.allocate_buffers(
                encoder_shape=self.trt_models["vae_encoder"].get_shape_dict(
                    batch_size, image_height, image_width
                ),
                decoder_shape=self.trt_models["vae"].get_shape_dict(
                    batch_size, image_height, image_width
                ),
                device=self.device,
            )

    def _encode_prompt(
        self,
        prompt: str,
        negative_prompt: str,
        num_images_per_prompt: int,
        do_classifier_free_guidance: bool,
    ):
        return super()._encode_prompt(
            prompt,
            negative_prompt,
            num_images_per_prompt,
            do_classifier_free_guidance,
            float16=True,
        )

    def encode_image(self, init_image):
        init_latents = self.vae.encode(init_image)
        init_latents = 0.18215 * init_latents
        return init_latents

    def prepare_latents(
        self,
        vae_scale_factor: int,
        unet_in_channels: int,
        image: Optional[torch.Tensor],
        timestep: torch.Tensor,
        batch_size: int,
        height: int,
        width: int,
        dtype: torch.dtype,
        generator: Generator,
        latents: torch.Tensor = None,
    ):
        dtype = torch.float32
        if image is not None and self.full_acceleration:
            image = image.to(self.device).to(dtype)
            image = image.repeat(batch_size, 1, 1, 1)
            init_latents = self.encode_image(image)
            noise = randn_tensor(
                init_latents.shape,
                generator=generator,
                device=self.device,
                dtype=dtype,
            )
            latents = self.scheduler.add_noise(init_latents, noise, timestep)
            return latents
        return super().prepare_latents(
            vae_scale_factor,
            unet_in_channels,
            image,
            timestep,
            batch_size,
            height,
            width,
            dtype,
            generator,
            latents,
        )

    def decode_latents(self, latents):
        if not self.full_acceleration:
            return super().decode_latents(latents)
        return self.vae.decode(latents).sample

    def decode_images(self, images: torch.Tensor):
        if not self.full_acceleration:
            return super().decode_images(images)
        images = (
            ((images + 1) * 255 / 2)
            .clamp(0, 255)
            .detach()
            .permute(0, 2, 3, 1)
            .round()
            .type(torch.uint8)
            .cpu()
            .numpy()
        )
        return [Image.fromarray(x) for x in images]
