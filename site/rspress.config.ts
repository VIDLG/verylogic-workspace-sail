import { defineConfig } from '@rspress/core';
import mermaid from 'rspress-plugin-mermaid';

const [githubOwner, githubRepo] = (process.env.GITHUB_REPOSITORY ?? '').split('/');
const isUserSite = githubRepo === `${githubOwner}.github.io`;
const base = githubOwner && githubRepo && !isUserSite ? `/${githubRepo}/` : '/';

export default defineConfig({
  root: 'docs',
  outDir: 'dist',
  base,
  lang: 'en',
  title: 'verylogic Sail ISA Workspace',
  description: 'Executable ISA models and teaching material built with Sail',
  locales: [
    {
      lang: 'en',
      label: 'English',
      title: 'verylogic Sail ISA Workspace',
      description: 'Executable ISA models and teaching material built with Sail',
    },
    {
      lang: 'zh',
      label: '简体中文',
      title: 'verylogic Sail ISA Workspace',
      description: '使用 Sail 编写、运行和学习指令集架构',
    },
  ],
  plugins: [
    mermaid({
      mermaidConfig: {
        securityLevel: 'strict',
      },
    }),
  ],
  themeConfig: {
    search: true,
    localeRedirect: 'never',
    sidebar: {
      '/': [
        {
          text: 'Workspace',
          items: [
            { text: 'Documentation home', link: '/' },
            { text: 'Why Sail', link: '/why-sail' },
            { text: 'Common teaching contract', link: '/reference/teaching-contract' },
          ],
        },
        {
          text: 'Hack',
          items: [
            { text: 'Overview', link: '/hack/' },
            { text: 'Tutorial', link: '/hack/tutorial' },
            { text: 'ISA guide', link: '/hack/isa' },
            { text: 'Evolve Hack', link: '/hack/evolution' },
          ],
        },
        {
          text: 'Hack advanced topics',
          items: [
            { text: 'Assembler', link: '/hack/assembler' },
            { text: 'Execution and tests', link: '/hack/execution' },
          ],
        },

      ],
      '/zh/': [
        {
          text: '工作区',
          items: [
            { text: '文档首页', link: '/zh/' },
            { text: '为什么选择 Sail', link: '/zh/why-sail' },
            { text: '公共教学契约', link: '/zh/reference/teaching-contract' },
          ],
        },
        {
          text: 'Hack',
          items: [
            { text: '概览', link: '/zh/hack/' },
            { text: '入门教程', link: '/zh/hack/tutorial' },
            { text: 'ISA 指南', link: '/zh/hack/isa' },
            { text: '进化 Hack', link: '/zh/hack/evolution' },
          ],
        },
        {
          text: 'Hack 高级主题',
          items: [
            { text: '汇编器', link: '/zh/hack/assembler' },
            { text: '执行器与测试', link: '/zh/hack/execution' },
          ],
        },

      ],
    },
  },
});
