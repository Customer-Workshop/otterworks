import toast from "react-hot-toast";
import { filesApi } from "./api";

/**
 * Download a file through the same-origin content endpoint, reporting a
 * visible started and finished (or failed) state to the user.
 */
export async function downloadFileToDisk(id: string, name: string): Promise<void> {
  const toastId = toast.loading(`Downloading ${name}…`);
  try {
    const blob = await filesApi.downloadContent(id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success(`Downloaded ${name}`, { id: toastId });
  } catch {
    toast.error(`Download failed for ${name}`, { id: toastId });
  }
}
