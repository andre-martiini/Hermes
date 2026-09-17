# Prompt — configurar deploy automático (CI/CD) do gestao-sigex via GitHub Actions

Contexto: hoje o deploy do `gestao-sigex` é manual (`firebase deploy --only hosting:gestao-sigex-site`, rodado por você ou por mim). O objetivo é fechar essa última etapa manual do fluxo: a partir de agora, todo merge em `main` deve disparar o deploy sozinho, sem comando manual — o mesmo resultado que já conseguimos no `argos-gestor-sistemas` (lá foi só um toggle nativo do App Hosting; aqui o repositório usa Firebase Hosting clássico, que não tem esse toggle, então o caminho é GitHub Actions).

Use o comando oficial do Firebase que já faz tudo isso automaticamente — cria os workflows do GitHub Actions E a credencial de serviço necessária, sem que ninguém precise copiar/colar uma chave manualmente:

```
cd sigex-gestao
firebase init hosting:github
```

Dados do projeto para conferir durante o assistente (já configurados no repositório, não devem mudar):
- Projeto Firebase: `gen-lang-client-0633332628`
- Hosting target: `gestao-sigex-site` (site `gestao-sigex`)
- Diretório público: `dist`
- Repositório GitHub: `andre-martiini/gestao-sigex`

## Roteiro do assistente (respostas esperadas)

1. "For which GitHub repository would you like to set up a GitHub workflow deploy?" → `andre-martiini/gestao-sigex`
2. Se pedir login/autorização no GitHub, autorize com a conta `andre-martiini` (é o próprio assistente do Firebase que cria o secret no repositório — não copie nem cole nenhuma chave manualmente em lugar nenhum).
3. "Set up the workflow to run a build script before every deploy?" → Yes
4. Script de build → `npm ci && npm run build` (o build já existente gera `dist`, confirmado antes por vocês)
5. "Set up automatic deployment to your site's live channel when a PR is merged?" → Yes
6. "What is the name of the GitHub branch associated with your site's live channel?" → `main`
7. Se perguntar sobre o `firebase.json` existente (public directory `dist`, single-page app rewrite), mantenha os valores já configurados — não sobrescreva com os padrões do assistente.

## O que isso cria

- `.github/workflows/firebase-hosting-merge.yml` — deploy para produção a cada merge em `main`.
- `.github/workflows/firebase-hosting-pull-request.yml` — preview channel temporário a cada PR (bônus: dá pra ver a mudança antes de mesclar).
- Um secret novo no repositório GitHub (service account do Firebase, criado e escopado automaticamente pelo assistente) — não precisa (nem deve) ser manuseado por fora dele.

Não revise o conteúdo gerado comigo antes de commitar — é um assistente oficial do próprio Firebase, gerando um workflow padrão. Só confirme visualmente, antes de dar push, que os dois arquivos `.yml` referenciam `gestao-sigex-site` (ou o alvo/site correto) e a branch `main`.

## Depois de configurado

```
git add .github/workflows/firebase-hosting-merge.yml .github/workflows/firebase-hosting-pull-request.yml
git commit -m "ci: deploy automático do Firebase Hosting via GitHub Actions no merge em main"
git push origin main
```

Teste fazendo um merge pequeno (pode ser um PR qualquer, até um ajuste trivial) e confirmando na aba "Actions" do GitHub que o workflow `firebase-hosting-merge` rodou e terminou com sucesso, e que `gestao-sigex.web.app` refletiu a mudança sem ninguém rodar `firebase deploy` manualmente.

Me avise quando terminar — a partir daí o `gestao-sigex` fecha o mesmo ciclo que o `argos-gestor-sistemas` já tem: merge por você (ou por mim, pelo conector), deploy sozinho.
