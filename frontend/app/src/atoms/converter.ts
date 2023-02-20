import type { ConvertDiffusersOptions } from 'internal:api'
import { atom } from 'jotai'

const OPTIONS: Required<ConvertDiffusersOptions> = {
    model_id: '',
    filename: '',
    reference_model: 'CompVis/stablediffusion-v1-4',
    hf_token: '',
}

export const converterFormAtom = atom(OPTIONS)
