// Modal e confirm compartilhados (#transbordo-modal / #transbordo-confirm),
// padrão adaptado do APP_Vector. Nenhuma tela desta fase usa isto ainda
// (ver spec 2026-08-23-fase5-ui-dados-cenarios-design.md, "Decisões em
// aberto") -- fica pronto para quando alguma ação futura precisar.
document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'transbordo-modal') {
        document.getElementById('transbordo-modal').showModal();
    }
});

document.body.addEventListener('htmx:confirm', function (evt) {
    if (!evt.detail.target.hasAttribute('data-confirm-custom')) return;
    evt.preventDefault();
    const dialogo = document.getElementById('transbordo-confirm');
    if (!dialogo) { evt.detail.issueRequest(true); return; }
    dialogo.showModal();
    dialogo.querySelector('[data-confirm-ok]').onclick = function () {
        dialogo.close();
        evt.detail.issueRequest(true);
    };
    dialogo.querySelector('[data-confirm-cancel]').onclick = function () {
        dialogo.close();
    };
});
