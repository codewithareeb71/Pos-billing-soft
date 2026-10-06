"""Thermal receipt and barcode-label rendering / printing.

Printing uses the Windows printer infrastructure (QPrinter) so any standard
printer - including 58mm and 80mm thermal receipt printers - can be used.
No vendor SDK is required.
"""
from __future__ import annotations

import html
import uuid
from pathlib import Path

from .. import config
from ..core.db import row, rows
from ..core.exceptions import PrintError
from ..core.money import format_minor, from_minor

MM_PER_INCH = 25.4


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


class ReceiptService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    # ------------------------------------------------------------ document
    @property
    def currency(self) -> str:
        return self.settings.currency

    def _logo_img(self, width_px: int = 110) -> str:
        if not self.settings.get_bool("receipt.show_logo", True):
            return ""
        logo = self.settings.get("shop.logo") or str(config.SHOP_LOGO_PATH)
        path = Path(logo)
        if not path.exists():
            return ""
        return (f'<div style="text-align:center;margin-bottom:4px;">'
                f'<img src="{esc(path.as_uri())}" width="{width_px}"/></div>')

    def receipt_html(self, sale: dict, note: str = "", reprint: bool = False) -> str:
        """Professional thermal receipt document."""
        width_mm = self.settings.receipt_width_mm
        s = self.settings
        show_barcode = s.get_bool("receipt.show_barcode", True)
        body_rows = []
        for item in sale["items"]:
            qty = float(item["quantity"])
            body_rows.append(
                "<tr>"
                f"<td class='item'>{esc(item['product_name'])}"
                + (f"<br/><span class='muted'>{esc(item['sku'])}</span>"
                   if s.get_bool("receipt.show_sku", False) and item["sku"] else "")
                + "</td>"
                f"<td class='num'>{qty:g}</td>"
                f"<td class='num'>{esc(format_minor(item['unit_price'], '', False))}</td>"
                f"<td class='num'>{esc(format_minor(item['line_total'], '', False))}</td>"
                "</tr>"
            )
            if int(item["discount_amount"] or 0):
                body_rows.append(
                    f"<tr><td class='disc' colspan='3'>Discount</td>"
                    f"<td class='num disc'>-{esc(format_minor(item['discount_amount'], '', False))}</td></tr>"
                )
        head = [
            f"<div class='shop'>{esc(s.shop_name)}</div>",
        ]
        if s.get_bool("receipt.show_address", True) and s.get("shop.address"):
            head.append(f"<div class='muted center'>{esc(s.get('shop.address'))}</div>")
        if s.get_bool("receipt.show_phone", True) and s.get("shop.phone"):
            head.append(f"<div class='muted center'>Phone: {esc(s.get('shop.phone'))}</div>")
        custom_header = s.get("receipt.header")
        if custom_header:
            head.append(f"<div class='center'>{esc(custom_header)}</div>")
        head.append("<hr/>")
        head.append(
            f"<table class='meta'><tr><td>Invoice</td><td class='right b'>{esc(sale['invoice_no'])}</td></tr>"
            f"<tr><td>Date</td><td class='right'>{esc(sale['created_at'])}</td></tr>"
        )
        if s.get_bool("receipt.show_cashier", True):
            head.append(f"<tr><td>Cashier</td><td class='right'>{esc(sale['cashier_name'])}</td></tr>")
        if s.get_bool("receipt.show_customer", True):
            head.append(f"<tr><td>Customer</td><td class='right'>{esc(sale.get('customer','Walk-in Customer'))}</td></tr>")
        if reprint:
            head.append(f"<tr><td colspan='2' class='center disc'>REPRINT</td></tr>")
        head.append("</table><hr/>")
        if note:
            head.append(f"<div class='center disc'>{esc(note)}</div>")

        table = (
            "<table class='items'><thead><tr><th>Item</th><th class='num'>Qty</th>"
            "<th class='num'>Price</th><th class='num'>Amount</th></tr></thead>"
            "<tbody>" + "".join(body_rows) + "</tbody></table>"
        )
        footer = ["<hr/>"]
        meta_rows = [
            ("Subtotal", format_minor(sale["subtotal"], "", False)),
        ]
        if int(sale["item_discount"] or 0):
            meta_rows.append(("Item discounts",
                              "-" + format_minor(sale["item_discount"], "", False)))
        if int(sale["bill_discount"] or 0):
            label = "Bill discount"
            if sale.get("bill_discount_type") == "Percentage":
                label += f" ({sale['bill_discount_value']}%)"
            meta_rows.append((label,
                              "-" + format_minor(sale["bill_discount"], "", False)))
        meta_rows.append(("TOTAL", format_minor(sale["total"], "", False)))
        meta_rows.append(("Paid", format_minor(sale["paid"], "", False)))
        meta_rows.append(("Change", format_minor(sale["change_due"], "", False)))
        meta_rows.append(("Payment", sale["payment_method"]))
        for label, value in meta_rows:
            css = " class='total'" if label == "TOTAL" else ""
            footer.append(
                f"<table class='totals'{css}><tr><td>{esc(label)}</td>"
                f"<td class='right'>{esc(value)}</td></tr></table>"
            )
        barcode_html = ""
        if show_barcode:
            image = self._barcode_image(sale["invoice_no"], kind="code128", height=40)
            if image:
                barcode_html = (f"<div class='center' style='margin-top:6px;'>"
                                f'<img src="{esc(Path(image).as_uri())}"/>'
                                f"<div class='muted'>{esc(sale['invoice_no'])}</div></div>")
        footer_html = "".join(footer)
        footer_message = s.get("receipt.footer") or ""
        end = ""
        if footer_message:
            end += f"<div class='center footer'>{esc(footer_message)}</div>"
        end += barcode_html
        currency = self.currency
        body = (
            "<div class='receipt'>"
            + self._logo_img()
            + "".join(head)
            + table
            + footer_html
            + end
            + "</div>"
        )
        return self._wrap(body, width_mm, currency_label=currency)

    def _wrap(self, body: str, width_mm: int, currency_label: str = "") -> str:
        font_pt = 8 if width_mm <= 60 else 9
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
        body {{ font-family: 'Consolas', 'Courier New', monospace; font-size: {font_pt}pt;
               color:#000; margin:0; }}
        .receipt {{ width:{width_mm - 6}mm; padding:2mm; }}
        .shop {{ font-size:{font_pt + 5}pt; font-weight:bold; text-align:center;
                 letter-spacing:1px; }}
        .center {{ text-align:center; }}
        .right {{ text-align:right; }}
        .right.b, .b {{ font-weight:bold; }}
        .muted {{ color:#444; font-size:{font_pt - 1}pt; }}
        .disc {{ color:#a00; }}
        .footer {{ margin-top:6px; font-size:{font_pt}pt; }}
        hr {{ border:none; border-top:1px dashed #000; margin:4px 0; }}
        table {{ width:100%; border-collapse:collapse; }}
        .items th {{ border-bottom:1px solid #000; font-size:{font_pt - 1}pt;
                     text-align:left; padding:2px 0; }}
        .items td {{ padding:2px 0; vertical-align:top; font-size:{font_pt}pt; }}
        .item {{ width:56%; }}
        .num {{ text-align:right; }}
        .meta td {{ padding:1px 0; font-size:{font_pt}pt; }}
        .totals {{ font-size:{font_pt}pt; padding:1px 0; }}
        .totals td {{ padding:1px 0; }}
        tr.total td {{ font-size:{font_pt + 3}pt; font-weight:bold; border-top:1px solid #000; }}
        </style></head><body>{body}</body></html>"""

    # --------------------------------------------------------------- print
    @staticmethod
    def _printer(printer_name: str = ""):
        from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

        printer = QPrinter(QPrinter.HighResolution)
        chosen = None
        if printer_name:
            for info in QPrinterInfo.availablePrinters():
                if info.printerName().lower() == printer_name.lower():
                    chosen = info
                    break
        if chosen is None:
            default = QPrinterInfo.defaultPrinter()
            available = QPrinterInfo.availablePrinters()
            chosen = default if default in available else (available[0] if available else None)
        if chosen:
            printer.setPrinterName(chosen.printerName())
        return printer

    @staticmethod
    def _set_page(printer, width_mm: int, height_mm: float = 297.0) -> None:
        from PySide6.QtCore import QSizeF
        from PySide6.QtGui import QPageLayout, QPageSize

        size = QSizeF(width_mm, height_mm)
        printer.setPageLayout(QPageLayout(size, QPageLayout.Millimeter,
                                          QMarginsF(0, 0, 0, 0),
                                          QPageLayout.MinimumMargins))
        printer.setFullPage(True)

    def print_html(self, html_text: str, width_mm: int | None = None,
                   printer_name: str = "", copies: int = 1) -> None:
        from PySide6.QtGui import QTextDocument

        width_mm = width_mm or self.settings.receipt_width_mm
        printer = self._printer(printer_name or self.settings.get("receipt.printer", ""))
        self._set_page(printer, width_mm, height_mm=200)
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setHtml(html_text)
        for _ in range(max(1, copies)):
            document.print_(printer)

    def print_text(self, text: str, width_mm: int | None = None,
                   printer_name: str = "") -> None:
        from PySide6.QtGui import QTextDocument

        width_mm = width_mm or self.settings.receipt_width_mm
        printer = self._printer(printer_name or self.settings.get("receipt.printer", ""))
        self._set_page(printer, width_mm, height_mm=200)
        document = QTextDocument()
        document.setDefaultFont(self._mono_font())
        document.setPlainText(text)
        document.print_(printer)

    @staticmethod
    def _mono_font():
        from PySide6.QtGui import QFont

        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        return font

    def preview(self, parent, html_text: str, width_mm: int | None = None,
                title: str = "Print preview") -> None:
        from PySide6.QtPrintSupport import QPrintPreviewDialog
        from PySide6.QtGui import QTextDocument

        width_mm = width_mm or self.settings.receipt_width_mm
        printer = self._printer(self.settings.get("receipt.printer", ""))
        self._set_page(printer, width_mm, height_mm=200)
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setHtml(html_text)

        def _paint(printer_obj, doc=document):
            doc.print_(printer_obj)

        dialog = QPrintPreviewDialog(printer, parent)
        dialog.setWindowTitle(title)
        dialog.paintRequested.connect(_paint)
        dialog.exec()

    def test_receipt_html(self) -> str:
        sale = {
            "invoice_no": "ALS-TEST-0001",
            "created_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cashier_name": "Test Cashier",
            "customer": "Walk-in Customer",
            "items": [
                {"product_name": "Example Product", "sku": "SKU-000001", "quantity": 2,
                 "unit_price": 15000, "line_total": 30000, "discount_amount": 0},
                {"product_name": "Second Product", "sku": "SKU-000002", "quantity": 1,
                 "unit_price": 12550, "line_total": 12550, "discount_amount": 550},
            ],
            "subtotal": 42550, "item_discount": 550, "bill_discount": 0,
            "bill_discount_type": "None", "bill_discount_value": 0,
            "total": 42000, "paid": 50000, "change_due": 8000,
            "payment_method": "Cash",
        }
        return self.receipt_html(sale, note="Test print - printer configuration check")

    # ------------------------------------------------------------- barcodes
    @staticmethod
    def _barcode_kind(code: str) -> str | None:
        code = (code or "").strip()
        if not code:
            return None
        if code.isdigit():
            if len(code) in (12, 13):
                return "ean13"
            if len(code) in (7, 8):
                return "ean8"
            if len(code) == 12:
                return "upca"
        return "code128"

    def _barcode_image(self, code: str, kind: str | None = None,
                       height: int = 40, width: int = 200) -> str | None:
        """Render a barcode to a PNG file (SVG -> QImage, no external tools)."""
        try:
            import barcode
            from barcode.writer import SVGWriter
        except Exception:  # pragma: no cover - optional dependency
            return None
        code = (code or "").strip()
        if not code:
            return None
        kind = kind or self._barcode_kind(code)
        try:
            if kind in ("ean13", "ean8", "upca"):
                digits = "".join(ch for ch in code if ch.isdigit())
                expected = {"ean13": 12, "ean8": 7, "upca": 11}[kind]
                if len(digits) < expected:
                    kind = "code128"
                else:
                    code = digits[:expected]
            instance = barcode.get(kind, code, writer=SVGWriter())
            svg_text = instance.render(
                writer_options={"module_height": height, "quiet_zone": True,
                                "font_size": 8, "text_distance": 6, "write_text": True}
            )
        except Exception:
            if kind == "code128":
                return None
            try:
                instance = barcode.get("code128", code, writer=SVGWriter())
                svg_text = instance.render(
                    writer_options={"module_height": height, "quiet_zone": True,
                                    "font_size": 8, "text_distance": 6, "write_text": True})
            except Exception:
                return None
        return self._svg_to_png(svg_text, width, height * 6)

    @staticmethod
    def _svg_to_png(svg_text, width: int, height: int) -> str | None:
        try:
            from PySide6.QtCore import QByteArray, QSize
            from PySide6.QtGui import QImage, QPainter, QGuiApplication
            from PySide6.QtSvg import QSvgRenderer
        except Exception:  # pragma: no cover
            return None
        if QGuiApplication.instance() is None:
            return None  # rendering needs a running Qt application
        payload = (svg_text.encode("utf-8") if isinstance(svg_text, str)
                   else bytes(svg_text))
        renderer = QSvgRenderer(QByteArray(payload))
        if not renderer.isValid():
            return None
        size = renderer.defaultSize()
        if size.width() <= 0 or size.height() <= 0:
            return None
        target = QSize(width, max(1, int(width * size.height() / size.width())))
        image = QImage(target, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        painter = QPainter(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        out_dir = config.ASSET_DIR / "barcodes"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{uuid.uuid4().hex}.png"
        if not image.save(str(path), "PNG"):
            return None
        return str(path)

    def barcode_image(self, code: str, height: int = 60) -> str | None:
        return self._barcode_image(code, height=height)

    # ---------------------------------------------------------- label sheet
    def labels_html(self, products: list[dict], show_price: bool = True,
                    show_name: bool = True, label_w_mm: int = 50,
                    label_h_mm: int = 30) -> str:
        cells = []
        for product in products:
            code = product.get("barcode") or product.get("sku") or ""
            image = self._barcode_image(code, height=34, width=300)
            img_html = (f'<img src="{esc(Path(image).as_uri())}"/>' if image
                        else f"<div class='code'>{esc(code)}</div>")
            price = ""
            if show_price and product.get("selling_price") is not None:
                price = (f"<div class='price'>{esc(format_minor(product['selling_price'], self.currency))}</div>")
            name = (f"<div class='name'>{esc(product.get('name',''))}</div>"
                    if show_name else "")
            cells.append(
                f"<td class='label' style='width:{label_w_mm}mm;height:{label_h_mm}mm;'>"
                f"{name}{img_html}{price}</td>"
            )
        rows_html = []
        for i in range(0, len(cells), 2):
            row_cells = cells[i:i + 2]
            while len(row_cells) < 2:
                row_cells.append("<td class='label'></td>")
            rows_html.append("<tr>" + "".join(row_cells) + "</tr>")
        body = f"""<div class='sheet'><table>{''.join(rows_html)}</table></div>"""
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
        body {{ font-family: Arial, sans-serif; font-size:7pt; margin:0; color:#000; }}
        table {{ border-collapse:collapse; width:100%; }}
        td.label {{ border:0 dotted #999; text-align:center; vertical-align:middle;
                    padding:1mm; overflow:hidden; }}
        .name {{ font-size:7pt; font-weight:bold; margin-bottom:1mm;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .price {{ font-size:9pt; font-weight:bold; margin-top:1mm; }}
        .code {{ font-family:'Consolas',monospace; font-size:8pt; }}
        img {{ max-width:44mm; }}
        </style></head><body>{body}</body></html>"""

    def print_labels(self, products: list[dict], show_price: bool = True,
                     show_name: bool = True, label_w_mm: int = 50,
                     label_h_mm: int = 30, printer_name: str = "") -> str:
        html_text = self.labels_html(products, show_price, show_name, label_w_mm, label_h_mm)
        self.print_html(html_text, width_mm=100, printer_name=printer_name)
        return html_text

    # ------------------------------------------------------------ helpers
    def available_printers(self) -> list[str]:
        try:
            from PySide6.QtPrintSupport import QPrinterInfo
            return [p.printerName() for p in QPrinterInfo.availablePrinters()]
        except Exception:  # pragma: no cover
            return []
