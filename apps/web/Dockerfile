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

FROM node:22-alpine AS runner
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]

