(() => {
    const itemSelect = document.getElementById("item_select");
    const qtyInput = document.getElementById("item_qty");
    const returnQtyInput = document.getElementById("return_qty");
    const priceInput = document.getElementById("item_price");
    const lineDiscountInput = document.getElementById("line_discount");
    const addLineBtn = document.getElementById("add-line-btn");
    const linesBody = document.getElementById("sale-lines-body");
    const linesJsonInput = document.getElementById("lines-json");
    const discountPercentInput = document.getElementById("discount_percent");
    const paidAmountInput = document.getElementById("paid_amount");
    const paymentTypeInput = document.getElementById("payment_type");
    const saleForm = document.getElementById("sale-form");
    const clearSaleBtn = document.getElementById("clear-sale-btn");

    if (!saleForm) return;

    let lines = [];

    const asNumber = (value) => {
        const parsed = parseFloat(value);
        return Number.isFinite(parsed) ? parsed : 0;
    };

    const money = (value) => asNumber(value).toFixed(2);

    function recalculateSummary() {
        const subtotal = lines.reduce((sum, row) => sum + row.line_total, 0);
        const discountPercent = asNumber(discountPercentInput.value);
        const discountAmount = (subtotal * discountPercent) / 100;
        const net = Math.max(subtotal - discountAmount, 0);
        let paidAmount = asNumber(paidAmountInput.value);

        if (paymentTypeInput.value === "Credit" && paidAmountInput.value === "") {
            paidAmount = 0;
        }

        if (paidAmount > net) {
            paidAmount = net;
            paidAmountInput.value = net.toFixed(2);
        }
        const balance = net - paidAmount;

        document.getElementById("sum_items").textContent = lines.length;
        document.getElementById("sum_subtotal").textContent = money(subtotal);
        document.getElementById("sum_discount").textContent = money(discountAmount);
        document.getElementById("sum_net").textContent = money(net);
        document.getElementById("sum_balance").textContent = money(balance);
        linesJsonInput.value = JSON.stringify(lines);
    }

    function renderLines() {
        if (lines.length === 0) {
            linesBody.innerHTML = `<tr><td colspan="9" class="text-center text-muted">No item lines added yet.</td></tr>`;
            recalculateSummary();
            return;
        }

        linesBody.innerHTML = lines
            .map(
                (line, index) => `
                    <tr>
                        <td>${index + 1}</td>
                        <td>${line.barcode}</td>
                        <td>${line.description}</td>
                        <td>${line.qty}</td>
                        <td>${line.return_qty}</td>
                        <td>${money(line.unit_price)}</td>
                        <td>${money(line.discount)}</td>
                        <td>${money(line.line_total)}</td>
                        <td><button type="button" class="btn btn-sm btn-danger remove-line-btn" data-index="${index}">X</button></td>
                    </tr>
                `
            )
            .join("");

        document.querySelectorAll(".remove-line-btn").forEach((button) => {
            button.addEventListener("click", (event) => {
                const index = parseInt(event.target.dataset.index, 10);
                lines.splice(index, 1);
                renderLines();
            });
        });

        recalculateSummary();
    }

    itemSelect.addEventListener("change", () => {
        const selected = itemSelect.selectedOptions[0];
        if (!selected || !selected.value) {
            priceInput.value = "";
            return;
        }
        priceInput.value = selected.dataset.price || "";
    });

    addLineBtn.addEventListener("click", () => {
        const selected = itemSelect.selectedOptions[0];
        if (!selected || !selected.value) {
            alert("Select an item first.");
            return;
        }

        const qty = asNumber(qtyInput.value);
        const returnQty = asNumber(returnQtyInput.value);
        const unitPrice = asNumber(priceInput.value || selected.dataset.price);
        const discount = asNumber(lineDiscountInput.value);

        const soldQty = Math.max(qty - returnQty, 0);
        const lineTotal = Math.max((soldQty * unitPrice) - discount, 0);

        lines.push({
            item_id: parseInt(selected.value, 10),
            barcode: selected.dataset.barcode || "",
            description: selected.dataset.name || "",
            qty,
            return_qty: returnQty,
            unit_price: unitPrice,
            discount,
            line_total: lineTotal,
        });

        qtyInput.value = "1";
        returnQtyInput.value = "0";
        lineDiscountInput.value = "0";
        renderLines();
    });

    discountPercentInput.addEventListener("input", recalculateSummary);
    paidAmountInput.addEventListener("input", recalculateSummary);
    paymentTypeInput.addEventListener("change", () => {
        if (paymentTypeInput.value === "Credit" && paidAmountInput.value === "") {
            paidAmountInput.value = "0";
        }
        recalculateSummary();
    });

    clearSaleBtn.addEventListener("click", () => {
        lines = [];
        setTimeout(renderLines, 0);
    });

    saleForm.addEventListener("submit", (event) => {
        if (lines.length === 0) {
            event.preventDefault();
            alert("Please add at least one item line before saving.");
            return;
        }
        linesJsonInput.value = JSON.stringify(lines);
    });

    renderLines();
})();
