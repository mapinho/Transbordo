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
        input.classList.add("tabulator-editor-numero");
        const mask = IMask(input, {
            mask: Number, radix: ",", thousandsSeparator: ".",
            scale: decimais, padFractionalZeros: false, normalizeZeros: true,
        });
        const valorAtual = cell.getValue();
        if (valorAtual !== null && valorAtual !== undefined && valorAtual !== "") {
            mask.typedValue = Number(valorAtual);
        }
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
                editorParams: { format: "yyyy-MM-dd" },
                formatter: "datetime",
                formatterParams: { inputFormat: "yyyy-MM-dd", outputFormat: "dd/MM/yyyy", invalidPlaceholder: "(data inválida)" },
            };
        }
        return { title: col.label, field: col.field, editable: false };
    });
}

const _tabulatorInstances = new Map();

function initGridEditor(tableElementId, colunasElementId, linhasElementId, formId, paramName) {
    paramName = paramName || "linhas_json";

    // Durante o "settle" do htmx (após trocar #cenario-content ao salvar
    // ou trocar de aba), o conteúdo antigo e o novo coexistem por
    // instantes com os mesmos ids, enquanto o htmx anima/remove o antigo.
    // Este <script> roda nesse meio-tempo, então document.getElementById
    // pode resolver para o elemento ANTIGO (prestes a ser removido) em
    // vez do novo -- o Tabulator é então construído sobre um nó que o
    // htmx remove logo em seguida, e o header perde a classe "tabulator"
    // (vira texto solto sem estilo). Detectamos essa duplicação e
    // reagendamos a inicialização para depois que o htmx terminar de
    // assentar o DOM, quando resta um único elemento com cada id.
    if (document.querySelectorAll("#" + tableElementId).length > 1) {
        document.body.addEventListener("htmx:afterSettle", function () {
            initGridEditor(tableElementId, colunasElementId, linhasElementId, formId, paramName);
        }, { once: true });
        return;
    }

    const colunas = JSON.parse(document.getElementById(colunasElementId).textContent);
    const linhas = JSON.parse(document.getElementById(linhasElementId).textContent);

    // Sem destruir a instância anterior, seus callbacks/timers internos
    // ficam órfãos na memória.
    const instanciaAnterior = _tabulatorInstances.get(tableElementId);
    if (instanciaAnterior) {
        instanciaAnterior.destroy();
    }

    const table = new Tabulator("#" + tableElementId, {
        data: linhas, layout: "fitColumns", columns: construirColunasTabulator(colunas),
    });
    _tabulatorInstances.set(tableElementId, table);

    document.getElementById(formId).addEventListener("htmx:configRequest", function (evt) {
        evt.detail.parameters[paramName] = JSON.stringify(table.getData());
    });

    return table;
}
