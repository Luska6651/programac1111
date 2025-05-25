/**
 * Arquivo JavaScript principal - E-commerce
 * Contém todas as funcionalidades do front-end
 */

document.addEventListener('DOMContentLoaded', function() {
    // =============================================
    // INICIALIZAÇÃO GERAL
    // =============================================
    
    // Inicializa tooltips do Bootstrap
    initTooltips();
    
    // Inicializa toasts de notificação
    initToasts();
    
    // Configurações gerais
    setupGlobalListeners();
    
    // =============================================
    // FUNCIONALIDADES DO PRODUTO
    // =============================================
    
    // Galeria de imagens do produto
    setupProductGallery();
    
    // Seletor de quantidade
    setupQuantitySelector();
    
    // Botão de adicionar ao carrinho
    setupAddToCart();
    
    // =============================================
    // FUNCIONALIDADES DO CARRINHO
    // =============================================
    
    // Atualização de quantidade no carrinho
    setupCartQuantityUpdate();
    
    // Remoção de itens do carrinho
    setupCartItemRemoval();
    
    // =============================================
    // FUNCIONALIDADES GERAIS
    // =============================================
    
    // Confirmações de ações importantes
    setupConfirmations();
    
    // Validação de formulários
    setupFormValidation();
    
    // Atualiza contador do carrinho
    updateCartCount();
});

// =============================================
// FUNÇÕES DE INICIALIZAÇÃO
// =============================================

function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function initToasts() {
    const toastElList = [].slice.call(document.querySelectorAll('.toast'));
    window.toastList = toastElList.map(function(toastEl) {
        return new bootstrap.Toast(toastEl, { autohide: true, delay: 5000 });
    });
}

function setupGlobalListeners() {
    // Dispara evento quando o carrinho é atualizado
    document.addEventListener('carrinhoUpdated', function() {
        updateCartCount();
        pulseCartIcon();
    });
}

// =============================================
// FUNÇÕES DE PRODUTO
// =============================================

function setupProductGallery() {
    const thumbs = document.querySelectorAll('.produto-thumb');
    const mainImage = document.querySelector('.produto-img-principal');
    
    if (thumbs && mainImage) {
        thumbs.forEach(thumb => {
            thumb.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Atualiza imagem principal
                const newSrc = this.href || this.dataset.image;
                if (newSrc) {
                    mainImage.classList.add('fade-out');
                    setTimeout(() => {
                        mainImage.src = newSrc;
                        mainImage.classList.remove('fade-out');
                        mainImage.classList.add('fade-in');
                        setTimeout(() => mainImage.classList.remove('fade-in'), 300);
                    }, 200);
                }
                
                // Ativa thumb selecionada
                thumbs.forEach(t => t.classList.remove('active'));
                this.classList.add('active');
            });
        });
    }
}

function setupQuantitySelector() {
    document.querySelectorAll('.btn-quantidade').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const input = this.closest('.input-group').querySelector('.quantidade-input');
            let value = parseInt(input.value) || 0;
            
            if (this.classList.contains('btn-minus') && value > 1) {
                value--;
            } else if (this.classList.contains('btn-plus')) {
                value++;
            }
            
            input.value = value;
            
            // Dispara evento de mudança
            const event = new Event('change');
            input.dispatchEvent(event);
        });
    });
}

function setupAddToCart() {
    document.querySelectorAll('.btn-add-to-cart').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            const productId = this.dataset.productId;
            const quantity = this.closest('.product-actions').querySelector('.quantidade-input')?.value || 1;
            
            // Feedback visual
            const originalHTML = this.innerHTML;
            this.innerHTML = `
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Adicionando...
            `;
            this.disabled = true;
            
            try {
                const response = await fetch(`/adicionar-carrinho/${productId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: `quantidade=${quantity}`
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showToast('success', data.message);
                    document.dispatchEvent(new Event('carrinhoUpdated'));
                } else {
                    showToast('danger', data.message || 'Erro ao adicionar ao carrinho');
                }
            } catch (error) {
                console.error('Erro:', error);
                showToast('danger', 'Erro ao conectar com o servidor');
            } finally {
                this.innerHTML = originalHTML;
                this.disabled = false;
            }
        });
    });
}

// =============================================
// FUNÇÕES DO CARRINHO
// =============================================

function setupCartQuantityUpdate() {
    document.querySelectorAll('.cart-item-quantity').forEach(input => {
        input.addEventListener('change', async function() {
            const cartItemId = this.dataset.cartItemId;
            const newQuantity = this.value;
            
            // Feedback visual
            this.disabled = true;
            const spinner = document.createElement('span');
            spinner.className = 'spinner-border spinner-border-sm ms-2';
            this.parentNode.appendChild(spinner);
            
            try {
                const response = await fetch(`/atualizar-carrinho/${cartItemId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ quantidade: newQuantity })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    document.dispatchEvent(new Event('carrinhoUpdated'));
                    updateCartTotal(data.total);
                } else {
                    showToast('danger', data.message || 'Erro ao atualizar carrinho');
                    this.value = this.dataset.oldValue;
                }
            } catch (error) {
                console.error('Erro:', error);
                showToast('danger', 'Erro ao conectar com o servidor');
                this.value = this.dataset.oldValue;
            } finally {
                this.disabled = false;
                spinner.remove();
            }
        });
    });
}

function setupCartItemRemoval() {
    document.querySelectorAll('.btn-remove-cart-item').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            if (!confirm('Tem certeza que deseja remover este item do carrinho?')) {
                return;
            }
            
            const cartItemId = this.dataset.cartItemId;
            
            // Feedback visual
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';
            this.disabled = true;
            
            try {
                const response = await fetch(`/remover-carrinho/${cartItemId}`, {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showToast('success', data.message);
                    document.dispatchEvent(new Event('carrinhoUpdated'));
                    // Remove o item da lista
                    this.closest('.cart-item').remove();
                    updateCartTotal(data.total);
                } else {
                    showToast('danger', data.message || 'Erro ao remover item');
                }
            } catch (error) {
                console.error('Erro:', error);
                showToast('danger', 'Erro ao conectar com o servidor');
            }
        });
    });
}

// =============================================
// FUNÇÕES GERAIS
// =============================================

function setupConfirmations() {
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

function setupFormValidation() {
    document.querySelectorAll('form.needs-validation').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!this.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            
            this.classList.add('was-validated');
        }, false);
    });
}

function updateCartCount() {
    fetch('/api/carrinho/count')
        .then(response => response.json())
        .then(data => {
            const cartCount = document.getElementById('cart-count');
            if (cartCount) {
                cartCount.textContent = data.count;
                data.count > 0 ? cartCount.classList.remove('d-none') : cartCount.classList.add('d-none');
            }
        })
        .catch(error => console.error('Erro ao atualizar contador:', error));
}

function updateCartTotal(total) {
    const totalElement = document.querySelector('.cart-total');
    if (totalElement) {
        totalElement.textContent = `R$ ${total.toFixed(2)}`;
    }
}

function pulseCartIcon() {
    const cartIcon = document.querySelector('.cart-icon');
    if (cartIcon) {
        cartIcon.classList.add('pulse');
        setTimeout(() => cartIcon.classList.remove('pulse'), 1000);
    }
}

function showToast(type, message) {
    const toastElement = document.getElementById('toastCarrinho');
    if (toastElement) {
        const toastHeader = toastElement.querySelector('.toast-header');
        const toastBody = toastElement.querySelector('.toast-body');
        
        // Atualiza classes de cor
        toastHeader.className = 'toast-header';
        toastHeader.classList.add(`bg-${type}`, 'text-white');
        
        // Atualiza mensagem
        toastBody.textContent = message;
        
        // Mostra o toast
        const toast = bootstrap.Toast.getInstance(toastElement) || new bootstrap.Toast(toastElement);
        toast.show();
    }
}

// =============================================
// UTILITÁRIOS
// =============================================

/**
 * Debounce function para limitar a frequência de execução
 * @param {Function} func - Função a ser executada
 * @param {number} wait - Tempo de espera em ms
 * @returns {Function}
 */
function debounce(func, wait) {
    let timeout;
    return function() {
        const context = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), wait);
    };
}

// Exporta funções para uso global (se necessário)
window.Ecommerce = {
    updateCartCount,
    showToast,
    pulseCartIcon
};