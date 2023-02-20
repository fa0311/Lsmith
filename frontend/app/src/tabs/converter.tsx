import {
  Button,
  Container,
  Input,
  Stack,
  Text,
  Box,
  Alert,
  Loader,
  Progress,
  Space,
} from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import type { ConvertDiffusersOptions } from 'internal:api'
import { useAtom } from 'jotai'
import { useState } from 'react'

import { api } from '~/api'
import { converterFormAtom } from '~/atoms/converter'

const Converter = () => {
  const [form, setForm] = useAtom(converterFormAtom)

  const [status, setStatus] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const onSubmit = () => convertEngine(form)

  const convertEngine = async (req: ConvertDiffusersOptions) => {
    try {
      setError(null)
      setSuccess(null)
      setStatus({
        message: 'loading...',
        progress: 0,
      })
      const response = await api.convertEngine({ convertDiffusersOptions: req })
      if (response.status == 'success') {
        setSuccess(`success! output: ${response.output}`)
      }
      setStatus(null)
    } catch (e) {
      setStatus(null)
      setError((e as Error).message)
    }
  }

  return (
    <Box
      h="100%"
      sx={{
        overflowY: 'auto',
      }}
    >
      <Container py={'md'}>
        <Text size={'lg'}>Convert diffusers from ckpt moodel on Hugging Face</Text>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit()
          }}
        >
          <Stack my={'sm'}>
            <Input.Wrapper label={'Hugging Face Model ID (required)'} withAsterisk>
              <Input
                placeholder="CompVis/stablediffusion-v1-4"
                defaultValue={form.model_id}
                onChange={(e) => setForm({ ...form, model_id: e.currentTarget.value })}
              />
            </Input.Wrapper>
            <Input.Wrapper label={'File Name (required)'} withAsterisk>
              <Input
                placeholder="******/****.ckpt"
                defaultValue={form.filename}
                onChange={(e) =>
                  setForm({
                    ...form,
                    filename: e.currentTarget.value,
                  })
                }
              />
            </Input.Wrapper>

            <Input.Wrapper label={'Hugging Face Access Token'}>
              <Input
                placeholder="hf_********************"
                defaultValue={form.hf_token}
                onChange={(e) =>
                  setForm({
                    ...form,
                    hf_token: e.currentTarget.value,
                  })
                }
              />
            </Input.Wrapper>

            <Input.Wrapper label={'Hugging Reference Model ID'}>
              <Input
                placeholder="CompVis/stablediffusion-v1-4"
                defaultValue={form.reference_model}
                onChange={(e) => setForm({ ...form, reference_model: e.currentTarget.value })}
              />
            </Input.Wrapper>

            <Space h={'md'} />

            {status ? (
              <Box w={'100%'}>
                <Alert title={'Processing...'}>
                  <Text>
                    This may take about 10 minutes. Please wait until the process is finished.
                  </Text>
                  <Progress sections={[{ value: status?.['progress'] * 100, color: 'blue' }]} />
                </Alert>
                <Button w={'100%'} my={'sm'} disabled>
                  <Loader p={'xs'} />
                </Button>
              </Box>
            ) : (
              <Button type={'submit'}>Convert</Button>
            )}

            {success && (
              <Box>
                <Alert
                  title={'Success!'}
                  color={'green'}
                  withCloseButton={true}
                  onClose={() => {
                    setSuccess(null)
                  }}
                >
                  <Text>{success}</Text>
                </Alert>
              </Box>
            )}
          </Stack>
        </form>

        {error && (
          <Box>
            <Alert icon={<IconInfoCircle />} title={'Something went wrong...'} color={'red'}>
              {error}
            </Alert>
          </Box>
        )}
      </Container>
    </Box>
  )
}

export default Converter
