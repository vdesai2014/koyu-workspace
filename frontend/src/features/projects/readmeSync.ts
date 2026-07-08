import { saveProjectReadmeDirect } from './api'

type TokenGetter = () => Promise<string | null>

export async function saveProjectReadme(
  projectId: string,
  markdown: string,
  getToken: TokenGetter,
) {
  await saveProjectReadmeDirect(projectId, markdown, getToken)
}
