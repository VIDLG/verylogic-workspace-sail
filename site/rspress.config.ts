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
          items: [{ text: 'Documentation home', link: '/' }],
        },
        {
          text: 'Hack',
          items: [
            { text: 'Overview', link: '/hack/' },
            { text: 'Tutorial', link: '/hack/tutorial' },
            { text: 'ISA guide', link: '/hack/isa' },
          ],
        },
        {
          text: 'Toolchain internals',
          items: [
            { text: 'Assembler', link: '/hack/assembler' },
            { text: 'Execution and tests', link: '/hack/execution' },
          ],
        },
      ],
      '/zh/': [
        {
          text: '工作区',
          items: [{ text: '文档首页', link: '/zh/' }],
        },
        {
          text: 'Hack',
          items: [
            { text: '概览', link: '/zh/hack/' },
            { text: '入门教程', link: '/zh/hack/tutorial' },
            { text: 'ISA 指南', link: '/zh/hack/isa' },
          ],
        },
        {
          text: '工具链内部原理',
          items: [
            { text: '汇编器', link: '/zh/hack/assembler' },
            { text: '执行器与测试', link: '/zh/hack/execution' },
          ],
        },
      ],
    },
  },
});
