function formatarNumeroPtBr(cell, decimais) {
    const valor = cell.getValue();
    if (valor === null || valor === undefined || valor === "") return "";
    return Number(valor).toLocaleString("pt-BR", {
        minimumFractionDigits: decimais, maximumFractionDigits: decimais,
    });
}

function editorNumeroPtBr(decimais) {
    return function (cell, onRendered, success, cancel) {
        const input = document.createElement("input");
        input.value = cell.getValue() ?? "";
        input.classList.add("tabulator-editor-numero");
        const mask = IMask(input, {
            mask: Number, radix: ",", thousandsSeparator: ".",
            scale: decimais, padFractionalZeros: false, normalizeZeros: true,
        });
        onRendered(function () { input.focus(); });
        function salvar() {
            success(mask.unmaskedValue === "" ? null : Number(mask.unmaskedValue));
        }
        input.addEventListener("blur", salvar);
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter") salvar();
            if (e.key === "Escape") cancel();
        });
        return input;
    };
}

function construirColunasTabulator(colunas) {
    return colunas.map(function (col) {
        if (col.visible === false) {
            return { title: col.label, field: col.field, visible: false };
        }
        if (col.type === "number" && col.editable) {
            const decimais = col.decimals ?? 1;
            return {
                title: col.label, field: col.field, hozAlign: "right",
                formatter: function (cell) { return formatarNumeroPtBr(cell, decimais); },
                editor: editorNumeroPtBr(decimais),
            };
        }
        if (col.type === "date" && col.editable) {
            return {
                title: col.label, field: col.field, editor: "date",
                editorParams: { format: "dd/MM/yyyy" },
                formatter: "datetime",
                formatterParams: { inputFormat: "yyyy-MM-dd", outputFormat: "dd/MM/yyyy", invalidPlaceholder: "(data inválida)" },
            };
        }
        return { title: col.label, field: col.field, editable: false };
    });
}

function initGridEditor(tableElementId, colunasElementId, linhasElementId, formId, paramName) {
    paramName = paramName || "linhas_json";
    const colunas = JSON.parse(document.getElementById(colunasElementId).textContent);
    const linhas = JSON.parse(document.getElementById(linhasElementId).textContent);

    const table = new Tabulator("#" + tableElementId, {
        data: linhas, layout: "fitColumns", columns: construirColunasTabulator(colunas),
    });

    document.getElementById(formId).addEventListener("htmx:configRequest", function (evt) {
        evt.detail.parameters[paramName] = JSON.stringify(table.getData());
    });

    return table;
}
