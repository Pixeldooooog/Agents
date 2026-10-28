import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rename, rm } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dir, "../..");
const release = await Bun.file(path.join(root, "otto.lock.json")).json();
const directory = path.join(root, ".otto");
const destination = path.join(directory, release.asset);
const digest = async (file: string) => createHash("sha256").update(await readFile(file)).digest("hex");
if (await Bun.file(destination).exists() && await digest(destination) === release.sha256) {
  console.log(`Otto ${release.tag} already verified`);
} else {
  await mkdir(directory, { recursive: true });
  const temporary = await mkdtemp(path.join(directory, "download-"));
  try {
    const result = Bun.spawnSync(["gh", "release", "download", release.tag, "--repo", release.repository, "--pattern", release.asset, "--dir", temporary], {
      stdout: "inherit", stderr: "inherit"
    });
    if (result.exitCode !== 0) throw new Error("Cannot download private Otto release. Run gh auth login with access to Otto; CI needs OTTO_READ_TOKEN.");
    const downloaded = path.join(temporary, release.asset);
    if (await digest(downloaded) !== release.sha256) throw new Error("Otto release checksum mismatch; refusing installation");
    await rename(downloaded, destination);
    console.log(`Verified Otto ${release.tag}`);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}
