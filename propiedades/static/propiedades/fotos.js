// Vista mínima de prueba: si falla el enlace externo, mostrar un reemplazo.
document.querySelectorAll("[data-foto-portada]").forEach((imagen) => {
    const mostrarReemplazo = () => {
        imagen.hidden = true;
        imagen.parentElement.querySelector("[data-foto-reemplazo]").hidden = false;
    };
    imagen.addEventListener("error", mostrarReemplazo);
    if (imagen.complete && imagen.naturalWidth === 0) mostrarReemplazo();
});
