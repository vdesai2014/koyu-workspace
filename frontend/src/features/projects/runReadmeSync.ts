import { saveRunReadmeDirect } from './api'

type TokenGetter = () => Promise<string | null>

export async function saveRunReadme(
  runId: string,
  markdown: string,
  getToken: TokenGetter,
) {
  await saveRunReadmeDirect(runId, markdown, getToken)
}
