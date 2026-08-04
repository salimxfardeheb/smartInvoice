/** Tests du formulaire de dépôt (appel API mocké). */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadForm, validateFile } from "@/components/invoices/UploadForm";
import { api } from "@/lib/api-client";
import type { Invoice } from "@/types";
import { makeInvoice } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: {
    depositInvoice: jest.fn(),
    listInvoices: jest.fn(),
  },
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

const mockedApi = api as jest.Mocked<typeof api>;

describe("UploadForm", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("dépose une facture avec fichier, numéro et fournisseur", async () => {
    const user = userEvent.setup();
    const created = makeInvoice({ id: 9, status: "Déposée" });
    mockedApi.depositInvoice.mockResolvedValue(created);
    const onSuccess = jest.fn();

    render(<UploadForm onSuccess={onSuccess} suppliers={[{ id: 42, name: "ACME SAS" }]} />);

    const file = new File(["%PDF-1.4"], "facture.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Document *"), file);
    await user.type(screen.getByLabelText("Numéro de facture *"), "FAC-2026-099");
    await user.selectOptions(screen.getByLabelText("Fournisseur *"), "42");

    await user.click(screen.getByRole("button", { name: "Déposer la facture" }));

    await waitFor(() => {
      expect(mockedApi.depositInvoice).toHaveBeenCalledTimes(1);
    });

    const formData = mockedApi.depositInvoice.mock.calls[0][0] as FormData;
    expect(formData.get("invoice_number")).toBe("FAC-2026-099");
    expect(formData.get("supplier_id")).toBe("42");
    expect((formData.get("file") as File).name).toBe("facture.pdf");
    expect(onSuccess).toHaveBeenCalledWith(created);
  });

  test("le bouton reste désactivé tant que le formulaire est incomplet", () => {
    render(<UploadForm suppliers={[]} />);
    expect(screen.getByRole("button", { name: "Déposer la facture" })).toBeDisabled();
  });

  test("affiche l'erreur de doublon renvoyée par l'API", async () => {
    const user = userEvent.setup();
    mockedApi.depositInvoice.mockRejectedValue(new Error("Doublon détecté."));

    render(<UploadForm onSuccess={jest.fn()} suppliers={[{ id: 42, name: "ACME SAS" }]} />);

    const file = new File(["%PDF-1.4"], "facture.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Document *"), file);
    await user.type(screen.getByLabelText("Numéro de facture *"), "FAC-2026-099");
    await user.selectOptions(screen.getByLabelText("Fournisseur *"), "42");
    await user.click(screen.getByRole("button", { name: "Déposer la facture" }));

    expect(await screen.findByText("Doublon détecté.")).toBeInTheDocument();
  });

  test("validateFile refuse un format non pris en charge", () => {
    const bad = new File(["MZ"], "virus.exe", { type: "application/x-msdownload" });
    expect(validateFile(bad)).toContain("Format non pris en charge");
  });

  test("validateFile refuse un fichier trop volumineux", () => {
    const big = new File([new ArrayBuffer(21 * 1024 * 1024)], "large.pdf", {
      type: "application/pdf",
    });
    expect(validateFile(big)).toContain("20 Mo maximum");
  });

  test("validateFile accepte un PDF valide", () => {
    const ok = new File(["%PDF-1.4"], "facture.pdf", { type: "application/pdf" });
    expect(validateFile(ok)).toBeNull();
  });

  test("affiche une erreur client quand le format est invalide", () => {
    render(<UploadForm suppliers={[{ id: 42, name: "ACME SAS" }]} />);

    const input = screen.getByLabelText("Document *");
    const file = new File(["MZ"], "facture.exe", { type: "application/x-msdownload" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByRole("alert")).toHaveTextContent("Format non pris en charge");
    expect(screen.getByRole("button", { name: "Déposer la facture" })).toBeDisabled();
  });

  test("affiche un aperçu pour une image sélectionnée", async () => {
    const user = userEvent.setup();
    render(<UploadForm suppliers={[{ id: 42, name: "ACME SAS" }]} />);

    const file = new File(["fake-image"], "facture.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Document *"), file);

    expect(screen.getByText(/Aperçu de facture\.png/)).toBeInTheDocument();
    expect(screen.getByAltText("Aperçu du document facture.png")).toBeInTheDocument();
  });

  test("affiche la progression pendant l'envoi", async () => {
    const user = userEvent.setup();
    const onSuccess = jest.fn();
    let resolve!: (invoice: Invoice) => void;
    mockedApi.depositInvoice.mockImplementation((_form, onProgress) => {
      onProgress?.(40);
      return new Promise<Invoice>((res) => {
        resolve = res;
      });
    });

    render(<UploadForm onSuccess={onSuccess} suppliers={[{ id: 42, name: "ACME SAS" }]} />);

    const file = new File(["%PDF-1.4"], "facture.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Document *"), file);
    await user.type(screen.getByLabelText("Numéro de facture *"), "FAC-2026-099");
    await user.selectOptions(screen.getByLabelText("Fournisseur *"), "42");
    await user.click(screen.getByRole("button", { name: "Déposer la facture" }));

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText(/Envoi : 40 %/)).toBeInTheDocument();

    resolve(makeInvoice({ id: 9 }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(makeInvoice({ id: 9 })));
  });
});
