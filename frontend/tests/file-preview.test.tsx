/** Tests de l'aperçu du fichier source (blob authentifié). */

import { render, screen } from "@testing-library/react";
import { FilePreview } from "@/components/invoices/FilePreview";
import { api } from "@/lib/api-client";
import { ApiError } from "@/lib/errors";
import { makeInvoice } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: {
    fetchFile: jest.fn(),
  },
}));

const mockedApi = api as jest.Mocked<typeof api>;

describe("FilePreview", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("affiche une image pour un fichier image", async () => {
    const invoice = makeInvoice({
      file_info: { original_filename: "scan.png", content_type: "image/png", size: 100 },
    });
    mockedApi.fetchFile.mockResolvedValue({
      blob: new Blob(["x"], { type: "image/png" }),
      contentType: "image/png",
    });

    render(<FilePreview invoice={invoice} />);

    const image = (await screen.findByRole("img", { name: "Aperçu du document FAC-2026-001" })) as HTMLImageElement;
    expect(image).toBeInTheDocument();
    expect(mockedApi.fetchFile).toHaveBeenCalledWith(1);
  });

  test("affiche un iframe pour un PDF", async () => {
    const invoice = makeInvoice();
    mockedApi.fetchFile.mockResolvedValue({
      blob: new Blob(["%PDF"], { type: "application/pdf" }),
      contentType: "application/pdf",
    });

    render(<FilePreview invoice={invoice} />);

    expect(
      await screen.findByTitle("Aperçu du document FAC-2026-001"),
    ).toBeInTheDocument();
  });

  test("affiche une erreur si le chargement échoue", async () => {
    mockedApi.fetchFile.mockRejectedValue(new ApiError(404, "Le fichier est introuvable."));
    render(<FilePreview invoice={makeInvoice()} />);
    expect(await screen.findByText("Le fichier est introuvable.")).toBeInTheDocument();
  });
});
