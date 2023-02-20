from api.tensorrt import (
    ConvertDiffusersOptions,
)
import os

from ..api_router import api

from huggingface_hub import hf_hub_download
import submodules.sd_scripts.library.model_util as model_util
from ..models.base import BaseResponseModel

from modules import config



class DiffusersConvertResponseModel(BaseResponseModel):
    status: str
    output: str

@api.post("/diffusers/convert", response_model=DiffusersConvertResponseModel)
def convert_engine(req: ConvertDiffusersOptions):
    reference_model = req.reference_model if req.reference_model == None else "CompVis/stable-diffusion-v1-4"
    if os.path.isfile(req.model_id):
        model_file = req.model_id
    elif req.filename is not None and os.path.isfile(os.path.join(req.model_id, req.filename)):
        model_file = os.path.join(req.model_id, req.filename)
    else:
        model_file = hf_hub_download(repo_id=req.model_id, filename=req.filename, token=req.hf_token)

    model_dir = os.path.join(
        config.get("diffusers_dir"),
        os.path.join("__local__", os.path.basename(req.model_id))
        if os.path.isabs(req.model_id)
        else req.model_id
    )

    text_encoder, vae, unet = model_util.load_models_from_stable_diffusion_checkpoint(False, model_file)
    model_util.save_diffusers_checkpoint(False, model_dir, text_encoder, unet, reference_model, vae)

    return DiffusersConvertResponseModel(status="success", output=model_dir)