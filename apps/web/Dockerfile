FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# This image builds apps/web standalone (no workspace root lockfile in the
# build context), so npm resolves the tree from scratch. Recent npm (>=10.9.8
# in node:22-alpine) crashes on that resolution with
# "Cannot read properties of null (reading 'edgesOut')" in arborist's peer-set
# loader. --legacy-peer-deps takes the resolution path that doesn't hit the bug;
# the workspace root lockfile + CI still validate the real dependency tree.
RUN npm install --legacy-peer-deps

# Runtime only needs next/react/react-dom (see package.json "dependencies") —
# eslint, typescript, vitest and their transitive deps were only ever needed
# to build. A separate prod-only install, not `npm prune` on the dev tree
# afterwards: `npm prune --omit=dev` on this no-lockfile, --legacy-peer-deps
# tree hung indefinitely locally (arborist re-resolving the whole tree, never
# returned) — a fresh, targeted install is the same operation npm already
# does reliably above, just scoped to fewer packages. Shipping fewer packages
# isn't just smaller: it's fewer packages for a future CVE to land in (this
# is also how a scan caught a CRITICAL in `tar`, pulled in by dev-only
# tooling that had no business being in the running container).
FROM node:22-alpine AS prod-deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --legacy-peer-deps

FROM node:22-alpine AS runner
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
RUN rm -rf node_modules
COPY --from=prod-deps /app/node_modules ./node_modules
# node:alpine ships an unprivileged `node` user (uid 1000) — use it instead
# of root, same reasoning as the API image.
RUN chown -R node:node /app
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
