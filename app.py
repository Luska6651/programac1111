from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, g
import sqlite3
import hashlib
from datetime import datetime
import os
from werkzeug.utils import secure_filename

# =============================================
# CONFIGURAÇÕES INICIAIS
# =============================================

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura_123'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'img', 'produtos')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB para uploads
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

# Adicionar app ao contexto do template
@app.context_processor
def inject_app_context():
    return dict(app=app)

# =============================================
# FUNÇÕES AUXILIARES
# =============================================

def get_db_connection():
    """Cria conexão com o banco de dados"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def criar_hash(senha):
    """Cria hash SHA-256 para senhas"""
    return hashlib.sha256(senha.encode()).hexdigest()

def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin():
    """Verifica se o usuário atual é admin"""
    return session.get('is_admin', False)

def login_required(f):
    """Decorator para rotas que requerem login"""
    def wrapper(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para acessar esta página', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    """Decorator para rotas que requerem admin"""
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash('Acesso restrito a administradores', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# =============================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# =============================================

def init_db():
    """Inicializa o banco de dados e tabelas"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        banido INTEGER DEFAULT 0 CHECK (banido IN (0, 1)),
        admin INTEGER DEFAULT 0 CHECK (admin IN (0, 1)),
        data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela de produtos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT NOT NULL,
        preco REAL NOT NULL,
        estoque INTEGER NOT NULL DEFAULT 0,
        categoria TEXT,
        data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela de imagens dos produtos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS produto_imagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto_id INTEGER NOT NULL,
        imagem_path TEXT NOT NULL,
        is_principal INTEGER DEFAULT 0,
        FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
    )
    """)
    
    # Tabela de carrinho
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS carrinho (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL DEFAULT 1,
        data_adicao TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE,
        UNIQUE(usuario_id, produto_id)
    )
    """)
    
    # Tabela de pedidos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        data_pedido TEXT DEFAULT CURRENT_TIMESTAMP,
        total REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pendente',
        forma_pagamento TEXT,
        endereco_entrega TEXT,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )
    """)
    
    # Itens do pedido
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedido_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        preco_unitario REAL NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
        FOREIGN KEY (produto_id) REFERENCES produtos(id)
    )
    """)
    
    # Criar usuário admin padrão se não existir
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO usuarios (nome, email, senha, admin)
        VALUES (?, ?, ?, ?)
        """, ('Administrador', 'admin@example.com', criar_hash('admin123'), 1))
        conn.commit()
    except Exception as e:
        print(f"Erro ao criar usuário admin: {e}")
        conn.rollback()
    finally:
        conn.close()

def atualizar_banco_dados():
    """Adiciona a coluna categoria se não existir"""
    conn = get_db_connection()
    try:
        # Verificar se a coluna já existe
        colunas = conn.execute("PRAGMA table_info(produtos)").fetchall()
        coluna_existe = any(col['name'] == 'categoria' for col in colunas)
        
        if not coluna_existe:
            conn.execute("ALTER TABLE produtos ADD COLUMN categoria TEXT")
            conn.commit()
            print("Coluna 'categoria' adicionada à tabela produtos")
    except Exception as e:
        print(f"Erro ao atualizar banco de dados: {e}")
        conn.rollback()
    finally:
        conn.close()

# =============================================
# ROTAS PÚBLICAS
# =============================================

@app.route('/')
def index():
    """Página inicial com produtos em destaque"""
    conn = get_db_connection()
    try:
        produtos = conn.execute("""
            SELECT p.*, pi.imagem_path 
            FROM produtos p
            LEFT JOIN produto_imagens pi ON p.id = pi.produto_id AND pi.is_principal = 1
            WHERE p.estoque > 0
            ORDER BY p.data_cadastro DESC
            LIMIT 8
        """).fetchall()
        return render_template('index.html', produtos=produtos)
    except Exception as e:
        print(f"Erro ao carregar produtos: {e}")
        return render_template('index.html', produtos=[])
    finally:
        conn.close()

@app.route('/produtos')
def listar_produtos():
    """Lista todos os produtos com opção de busca"""
    busca = request.args.get('busca', '')
    categoria = request.args.get('categoria', '')
    
    conn = get_db_connection()
    try:
        query = """
            SELECT p.*, pi.imagem_path 
            FROM produtos p
            LEFT JOIN produto_imagens pi ON p.id = pi.produto_id AND pi.is_principal = 1
            WHERE p.estoque > 0
        """
        params = []
        
        if busca:
            query += " AND (p.nome LIKE ? OR p.descricao LIKE ?)"
            params.extend([f'%{busca}%', f'%{busca}%'])
        
        if categoria:
            query += " AND p.categoria = ?"
            params.append(categoria)
        
        query += " ORDER BY p.nome"
        
        produtos = conn.execute(query, params).fetchall()
        categorias = conn.execute("SELECT DISTINCT categoria FROM produtos WHERE categoria IS NOT NULL").fetchall()
        
        return render_template('produtos.html', 
                            produtos=produtos,
                            categorias=categorias,
                            busca=busca,
                            categoria_selecionada=categoria)
    except Exception as e:
        print(f"Erro ao buscar produtos: {e}")
        return render_template('produtos.html', produtos=[])
    finally:
        conn.close()

@app.route('/produto/<int:id>')
def detalhes_produto(id):
    """Página de detalhes de um produto específico"""
    conn = get_db_connection()
    try:
        produto = conn.execute("""
            SELECT * FROM produtos WHERE id = ?
        """, (id,)).fetchone()
        
        if not produto:
            flash('Produto não encontrado', 'danger')
            return redirect(url_for('listar_produtos'))
        
        imagens = conn.execute("""
            SELECT * FROM produto_imagens 
            WHERE produto_id = ?
            ORDER BY is_principal DESC
        """, (id,)).fetchall()
        
        return render_template('detalhes_produto.html', 
                             produto=produto,
                             imagens=imagens)
    except Exception as e:
        print(f"Erro ao carregar produto: {e}")
        flash('Erro ao carregar produto', 'danger')
        return redirect(url_for('listar_produtos'))
    finally:
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Rota de login"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '').strip()
        
        if not email or not senha:
            flash('Preencha todos os campos', 'danger')
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        try:
            usuario = conn.execute("""
                SELECT id, nome, senha, banido, admin 
                FROM usuarios 
                WHERE email = ?
            """, (email,)).fetchone()
            
            if usuario and usuario['senha'] == criar_hash(senha):
                if usuario['banido']:
                    flash('Sua conta está suspensa', 'danger')
                    return redirect(url_for('login'))
                
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                session['is_admin'] = bool(usuario['admin'])
                
                flash('Login realizado com sucesso!', 'success')
                return redirect(url_for('index'))
            
            flash('Email ou senha incorretos', 'danger')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Erro no login: {e}")
            flash('Erro ao processar login', 'danger')
            return redirect(url_for('login'))
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """Rota de cadastro de novos usuários"""
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()
        
        if not all([nome, email, senha, confirmar_senha]):
            flash('Preencha todos os campos', 'danger')
            return redirect(url_for('cadastro'))
        
        if senha != confirmar_senha:
            flash('As senhas não coincidem', 'danger')
            return redirect(url_for('cadastro'))
        
        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres', 'danger')
            return redirect(url_for('cadastro'))
        
        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO usuarios (nome, email, senha)
                VALUES (?, ?, ?)
            """, (nome, email, criar_hash(senha)))
            conn.commit()
            flash('Cadastro realizado com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Este email já está cadastrado', 'danger')
            return redirect(url_for('cadastro'))
        except Exception as e:
            print(f"Erro no cadastro: {e}")
            flash('Erro ao cadastrar usuário', 'danger')
            return redirect(url_for('cadastro'))
        finally:
            conn.close()
    
    return render_template('cadastro.html')

@app.route('/logout')
def logout():
    """Rota de logout"""
    session.clear()
    flash('Você foi desconectado', 'info')
    return redirect(url_for('index'))

# =============================================
# ROTAS DO CARRINHO
# =============================================

@app.route('/carrinho')
@login_required
def ver_carrinho():
    conn = get_db_connection()
    try:
        itens = conn.execute("""
            SELECT 
                c.id as carrinho_id,
                p.id as produto_id, 
                p.nome, 
                p.preco, 
                c.quantidade, 
                (p.preco * c.quantidade) as total_item,
                (SELECT imagem_path FROM produto_imagens 
                 WHERE produto_id = p.id LIMIT 1) as imagem_path
            FROM carrinho c
            JOIN produtos p ON c.produto_id = p.id
            WHERE c.usuario_id = ?
        """, (session['usuario_id'],)).fetchall()
        
        total = sum(item['total_item'] for item in itens)
        return render_template('carrinho.html', itens=itens, total=total)
    except Exception as e:
        print(f"Erro ao carregar carrinho: {e}")
        flash('Erro ao carregar carrinho', 'danger')
        return render_template('carrinho.html', itens=[], total=0)
    finally:
        conn.close()

@app.route('/adicionar-carrinho/<int:produto_id>', methods=['POST'])
@login_required
def adicionar_carrinho(produto_id):
    quantidade = request.form.get('quantidade', default=1, type=int)
    
    if not produto_id or quantidade < 1:
        return jsonify({'success': False, 'message': 'Dados inválidos'}), 400
    
    conn = get_db_connection()
    try:
        # Verificar estoque
        produto = conn.execute("""
            SELECT estoque FROM produtos WHERE id = ?
        """, (produto_id,)).fetchone()
        
        if not produto:
            return jsonify({'success': False, 'message': 'Produto não encontrado'}), 404
        
        # Verificar se já está no carrinho
        item = conn.execute("""
            SELECT id, quantidade FROM carrinho 
            WHERE usuario_id = ? AND produto_id = ?
        """, (session['usuario_id'], produto_id)).fetchone()
        
        nova_quantidade = quantidade + (item['quantidade'] if item else 0)
        
        if nova_quantidade > produto['estoque']:
            return jsonify({
                'success': False, 
                'message': f'Estoque insuficiente. Disponível: {produto["estoque"]}'
            }), 400
        
        if item:
            conn.execute("""
                UPDATE carrinho 
                SET quantidade = ?, data_adicao = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (nova_quantidade, item['id']))
        else:
            conn.execute("""
                INSERT INTO carrinho (usuario_id, produto_id, quantidade)
                VALUES (?, ?, ?)
            """, (session['usuario_id'], produto_id, quantidade))
        
        conn.commit()
        
        # Contar itens no carrinho
        total_itens = conn.execute("""
            SELECT COUNT(*) FROM carrinho WHERE usuario_id = ?
        """, (session['usuario_id'],)).fetchone()[0]
        
        return jsonify({
            'success': True,
            'message': 'Produto adicionado ao carrinho',
            'total_itens': total_itens
        })
    except Exception as e:
        conn.rollback()
        print(f"Erro ao adicionar ao carrinho: {e}")
        return jsonify({'success': False, 'message': 'Erro interno'}), 500
    finally:
        conn.close()

@app.route('/remover-carrinho/<int:item_id>', methods=['POST'])
@login_required
def remover_carrinho(item_id):
    """Remove item do carrinho"""
    conn = get_db_connection()
    try:
        # Verificar se o item pertence ao usuário
        item = conn.execute("""
            SELECT id FROM carrinho 
            WHERE id = ? AND usuario_id = ?
        """, (item_id, session['usuario_id'])).fetchone()
        
        if not item:
            flash('Item não encontrado', 'danger')
            return redirect(url_for('ver_carrinho'))
        
        conn.execute("DELETE FROM carrinho WHERE id = ?", (item_id,))
        conn.commit()
        flash('Item removido do carrinho', 'success')
        return redirect(url_for('ver_carrinho'))
    except Exception as e:
        conn.rollback()
        print(f"Erro ao remover item: {e}")
        flash('Erro ao remover item', 'danger')
        return redirect(url_for('ver_carrinho'))
    finally:
        conn.close()

@app.route('/atualizar-carrinho', methods=['POST'])
@login_required
def atualizar_carrinho():
    """Atualiza quantidades no carrinho"""
    conn = get_db_connection()
    try:
        for item_id, quantidade in request.form.items():
            if not item_id.startswith('quantidade-'):
                continue
                
            item_id = item_id.replace('quantidade-', '')
            
            # Verificar se o item pertence ao usuário
            item = conn.execute("""
                SELECT c.id, p.estoque 
                FROM carrinho c
                JOIN produtos p ON c.produto_id = p.id
                WHERE c.id = ? AND c.usuario_id = ?
            """, (item_id, session['usuario_id'])).fetchone()
            
            if not item:
                continue
                
            quantidade = int(quantidade)
            if quantidade < 1:
                conn.execute("DELETE FROM carrinho WHERE id = ?", (item_id,))
            elif quantidade > item['estoque']:
                flash(f'Quantidade maior que o estoque disponível ({item["estoque"]}) para um item', 'warning')
            else:
                conn.execute("""
                    UPDATE carrinho 
                    SET quantidade = ? 
                    WHERE id = ?
                """, (quantidade, item_id))
        
        conn.commit()
        flash('Carrinho atualizado', 'success')
        return redirect(url_for('ver_carrinho'))
    except Exception as e:
        conn.rollback()
        print(f"Erro ao atualizar carrinho: {e}")
        flash('Erro ao atualizar carrinho', 'danger')
        return redirect(url_for('ver_carrinho'))
    finally:
        conn.close()

@app.route('/api/carrinho/count')
@login_required
def api_carrinho_count():
    conn = get_db_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM carrinho WHERE usuario_id = ?", 
                           (session['usuario_id'],)).fetchone()[0]
        return jsonify({'count': count})
    finally:
        conn.close()

@app.route('/pedidos/<int:pedido_id>/cancelar', methods=['POST'])
@login_required
def cancelar_pedido(pedido_id):
    conn = get_db_connection()
    try:
        # Verificar se o pedido pertence ao usuário
        pedido = conn.execute("""
            SELECT id, status FROM pedidos 
            WHERE id = ? AND usuario_id = ?
        """, (pedido_id, session['usuario_id'])).fetchone()
        
        if not pedido:
            flash('Pedido não encontrado', 'danger')
            return redirect(url_for('meus_pedidos'))
        
        if pedido['status'] != 'pendente':
            flash('Só é possível cancelar pedidos pendentes', 'danger')
            return redirect(url_for('meus_pedidos'))
        
        # Atualizar status do pedido
        conn.execute("""
            UPDATE pedidos 
            SET status = 'cancelado' 
            WHERE id = ?
        """, (pedido_id,))
        
        # Devolver itens ao estoque
        itens = conn.execute("""
            SELECT produto_id, quantidade FROM pedido_itens 
            WHERE pedido_id = ?
        """, (pedido_id,)).fetchall()
        
        for item in itens:
            conn.execute("""
                UPDATE produtos 
                SET estoque = estoque + ? 
                WHERE id = ?
            """, (item['quantidade'], item['produto_id']))
        
        conn.commit()
        flash('Pedido cancelado com sucesso', 'success')
    except Exception as e:
        conn.rollback()
        print(f"Erro ao cancelar pedido: {e}")
        flash('Erro ao cancelar pedido', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('meus_pedidos'))

# =============================================
# ROTAS DE PEDIDOS
# =============================================

@app.route('/finalizar-pedido', methods=['GET', 'POST'])
@login_required
def finalizar_pedido():
    conn = get_db_connection()
    try:
        # Verificar itens no carrinho
        itens = conn.execute("""
            SELECT c.id, p.id as produto_id, p.nome, p.preco, p.estoque, c.quantidade
            FROM carrinho c
            JOIN produtos p ON c.produto_id = p.id
            WHERE c.usuario_id = ?
        """, (session['usuario_id'],)).fetchall()
        
        if not itens:
            flash('Seu carrinho está vazio', 'warning')
            return redirect(url_for('ver_carrinho'))
        
        # Verificar estoque e calcular total
        total = 0
        problemas = []
        for item in itens:
            if item['quantidade'] > item['estoque']:
                problemas.append(f"{item['nome']} (estoque: {item['estoque']}, solicitado: {item['quantidade']})")
            total += item['preco'] * item['quantidade']
        
        if problemas:
            flash('Sem estoque suficiente para: ' + ', '.join(problemas), 'danger')
            return redirect(url_for('ver_carrinho'))
        
        if request.method == 'POST':
            forma_pagamento = request.form.get('forma_pagamento', '').strip()
            endereco_entrega = request.form.get('endereco_entrega', '').strip()
            
            if not all([forma_pagamento, endereco_entrega]):
                flash('Preencha todos os campos obrigatórios', 'danger')
                return redirect(url_for('finalizar_pedido'))
            
            # Criar pedido
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pedidos (usuario_id, total, forma_pagamento, endereco_entrega)
                VALUES (?, ?, ?, ?)
            """, (session['usuario_id'], total, forma_pagamento, endereco_entrega))
            pedido_id = cursor.lastrowid
            
            # Adicionar itens ao pedido e atualizar estoque
            for item in itens:
                cursor.execute("""
                    INSERT INTO pedido_itens (pedido_id, produto_id, quantidade, preco_unitario)
                    VALUES (?, ?, ?, ?)
                """, (pedido_id, item['produto_id'], item['quantidade'], item['preco']))
                
                # Atualizar estoque
                novo_estoque = item['estoque'] - item['quantidade']
                cursor.execute("""
                    UPDATE produtos 
                    SET estoque = ? 
                    WHERE id = ?
                """, (novo_estoque, item['produto_id']))
            
            # Limpar carrinho
            cursor.execute("""
                DELETE FROM carrinho 
                WHERE usuario_id = ?
            """, (session['usuario_id'],))
            
            conn.commit()
            
            flash('Pedido realizado com sucesso!', 'success')
            return redirect(url_for('pedido_concluido', pedido_id=pedido_id))
        
        return render_template('finalizar_pedido.html', total=total)
    except Exception as e:
        conn.rollback()
        print(f"Erro ao finalizar pedido: {e}")
        flash('Erro ao finalizar pedido', 'danger')
        return redirect(url_for('ver_carrinho'))
    finally:
        conn.close()

@app.route('/pedido-concluido/<int:pedido_id>')
@login_required
def pedido_concluido(pedido_id):
    conn = get_db_connection()
    try:
        pedido = conn.execute("""
            SELECT * FROM pedidos 
            WHERE id = ? AND usuario_id = ?
        """, (pedido_id, session['usuario_id'])).fetchone()
        
        if not pedido:
            flash('Pedido não encontrado', 'danger')
            return redirect(url_for('meus_pedidos'))
        
        itens = conn.execute("""
            SELECT pi.*, p.nome, p.descricao, img.imagem_path
            FROM pedido_itens pi
            JOIN produtos p ON pi.produto_id = p.id
            LEFT JOIN produto_imagens img ON p.id = img.produto_id AND img.is_principal = 1
            WHERE pi.pedido_id = ?
        """, (pedido_id,)).fetchall()
        
        return render_template('pedido_concluido.html', 
                            pedido=pedido,
                            itens=itens)
    finally:
        conn.close()

@app.route('/meus-pedidos')
@login_required
def meus_pedidos():
    """Exibe o histórico de pedidos do usuário"""
    conn = get_db_connection()
    try:
        pedidos = conn.execute("""
            SELECT p.*, 
                   (SELECT COUNT(*) FROM pedido_itens WHERE pedido_id = p.id) as total_itens
            FROM pedidos p
            WHERE p.usuario_id = ?
            ORDER BY p.data_pedido DESC
        """, (session['usuario_id'],)).fetchall()
        
        return render_template('meus_pedidos.html', pedidos=pedidos)
    except Exception as e:
        print(f"Erro ao carregar pedidos: {e}")
        flash('Erro ao carregar pedidos', 'danger')
        return render_template('meus_pedidos.html', pedidos=[])
    finally:
        conn.close()

@app.route('/pedido/<int:pedido_id>')
@login_required
def detalhes_pedido(pedido_id):
    """Exibe detalhes de um pedido específico"""
    conn = get_db_connection()
    try:
        # Verificar se o pedido pertence ao usuário
        pedido = conn.execute("""
            SELECT * FROM pedidos 
            WHERE id = ? AND usuario_id = ?
        """, (pedido_id, session['usuario_id'])).fetchone()
        
        if not pedido:
            flash('Pedido não encontrado', 'danger')
            return redirect(url_for('meus_pedidos'))
        
        itens = conn.execute("""
            SELECT pi.*, p.nome, p.descricao, 
                   (pi.quantidade * pi.preco_unitario) as total_item,
                   img.imagem_path
            FROM pedido_itens pi
            JOIN produtos p ON pi.produto_id = p.id
            LEFT JOIN produto_imagens img ON p.id = img.produto_id AND img.is_principal = 1
            WHERE pi.pedido_id = ?
        """, (pedido_id,)).fetchall()
        
        return render_template('detalhes_pedido.html', 
                             pedido=pedido,
                             itens=itens)
    except Exception as e:
        print(f"Erro ao carregar pedido: {e}")
        flash('Erro ao carregar pedido', 'danger')
        return redirect(url_for('meus_pedidos'))
    finally:
        conn.close()

# =============================================
# ROTAS DE ADMINISTRAÇÃO
# =============================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Painel de controle administrativo"""
    conn = get_db_connection()
    try:
        # Estatísticas básicas
        estatisticas = {
            'total_produtos': conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] or 0,
            'total_usuarios': conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] or 0,
            'total_pedidos': conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] or 0,
            'pedidos_pendentes': conn.execute("SELECT COUNT(*) FROM pedidos WHERE status = 'pendente'").fetchone()[0] or 0,
            'vendas_totais': float(conn.execute("SELECT COALESCE(SUM(total), 0) FROM pedidos WHERE status = 'completo'").fetchone()[0] or 0)
        }
        
        # Últimos pedidos (5 mais recentes)
        ultimos_pedidos = conn.execute("""
            SELECT p.id, p.data_pedido, p.total, p.status, u.nome as cliente
            FROM pedidos p
            JOIN usuarios u ON p.usuario_id = u.id
            ORDER BY p.data_pedido DESC
            LIMIT 5
        """).fetchall()
        
        # Produtos com estoque baixo (menos de 5 unidades)
        produtos_baixo_estoque = conn.execute("""
            SELECT id, nome, estoque 
            FROM produtos 
            WHERE estoque < 5 AND estoque > 0
            ORDER BY estoque ASC
            LIMIT 5
        """).fetchall()
        
        return render_template('admin/dashboard.html',
                            estatisticas=estatisticas,
                            ultimos_pedidos=ultimos_pedidos,
                            produtos_baixo_estoque=produtos_baixo_estoque)
    
    except Exception as e:
        print(f"Erro no dashboard admin: {str(e)}")
        flash('Erro ao carregar o dashboard. Detalhes no console.', 'danger')
        return redirect(url_for('admin_produtos'))
    
    finally:
        conn.close()

@app.route('/admin/produtos')
@admin_required
def admin_produtos():
    """Listagem de produtos para administradores"""
    conn = get_db_connection()
    try:
        busca = request.args.get('busca', '')
        categoria = request.args.get('categoria', '')
        
        query = """
            SELECT p.*, 
                   (SELECT imagem_path FROM produto_imagens WHERE produto_id = p.id LIMIT 1) as imagem_principal,
                   (SELECT COUNT(*) FROM produto_imagens WHERE produto_id = p.id) as total_imagens
            FROM produtos p
            WHERE 1=1
        """
        params = []
        
        if busca:
            query += " AND (p.nome LIKE ? OR p.descricao LIKE ?)"
            params.extend([f'%{busca}%', f'%{busca}%'])
        
        if categoria:
            query += " AND p.categoria = ?"
            params.append(categoria)
        
        query += " ORDER BY p.nome"
        
        produtos = conn.execute(query, params).fetchall()
        categorias = conn.execute("SELECT DISTINCT categoria FROM produtos WHERE categoria IS NOT NULL").fetchall()
        
        return render_template('admin/produtos.html',
                            produtos=produtos,
                            categorias=categorias,
                            busca=busca,
                            categoria_selecionada=categoria)
    except Exception as e:
        print(f"Erro ao listar produtos (admin): {e}")
        flash('Erro ao carregar produtos', 'danger')
        return render_template('admin/produtos.html', produtos=[])
    finally:
        conn.close()

@app.route('/admin/produtos/novo', methods=['GET', 'POST'])
@admin_required
def admin_novo_produto():
    """Cadastro de novos produtos"""
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        preco = request.form.get('preco', type=float)
        estoque = request.form.get('estoque', default=0, type=int)
        categoria = request.form.get('categoria', '').strip()
        imagens = request.files.getlist('imagens')
        
        if not all([nome, descricao, preco is not None, estoque is not None]):
            flash('Preencha todos os campos obrigatórios', 'danger')
            return redirect(url_for('admin_novo_produto'))
        
        if preco <= 0:
            flash('O preço deve ser maior que zero', 'danger')
            return redirect(url_for('admin_novo_produto'))
        
        if estoque < 0:
            flash('O estoque não pode ser negativo', 'danger')
            return redirect(url_for('admin_novo_produto'))
        
        if len(imagens) < 1:
            flash('Adicione pelo menos uma imagem', 'danger')
            return redirect(url_for('admin_novo_produto'))
        
        conn = get_db_connection()
        try:
            # Inserir produto
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO produtos (nome, descricao, preco, estoque, categoria)
                VALUES (?, ?, ?, ?, ?)
            """, (nome, descricao, preco, estoque, categoria if categoria else None))
            produto_id = cursor.lastrowid
            
            # Processar imagens
            for i, imagem in enumerate(imagens):
                if imagem and allowed_file(imagem.filename):
                    filename = secure_filename(f"{produto_id}_{i}.{imagem.filename.rsplit('.', 1)[1].lower()}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    imagem.save(filepath)
                    
                    # Primeira imagem é definida como principal
                    is_principal = 1 if i == 0 else 0
                    cursor.execute("""
                        INSERT INTO produto_imagens (produto_id, imagem_path, is_principal)
                        VALUES (?, ?, ?)
                    """, (produto_id, filename, is_principal))
            
            conn.commit()
            flash('Produto cadastrado com sucesso!', 'success')
            return redirect(url_for('admin_produtos'))
        except Exception as e:
            conn.rollback()
            print(f"Erro ao cadastrar produto: {e}")
            flash('Erro ao cadastrar produto', 'danger')
            return redirect(url_for('admin_novo_produto'))
        finally:
            conn.close()
    
    return render_template('admin/novo_produto.html')

@app.template_filter('format_datetime')
def format_datetime(value, format='%d/%m/%Y %H:%M'):
    if value is None:
        return ""
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime(format)
    except:
        return value

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.route('/admin/produtos/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_editar_produto(id):
    """Edição de produtos existentes"""
    conn = get_db_connection()
    try:
        produto = conn.execute("""
            SELECT * FROM produtos WHERE id = ?
        """, (id,)).fetchone()
        
        if not produto:
            flash('Produto não encontrado', 'danger')
            return redirect(url_for('admin_produtos'))
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()
            preco = request.form.get('preco', type=float)
            estoque = request.form.get('estoque', type=int)
            categoria = request.form.get('categoria', '').strip()
            imagens = request.files.getlist('imagens')
            imagem_principal = request.form.get('imagem_principal', type=int)
            
            if not all([nome, descricao, preco is not None, estoque is not None]):
                flash('Preencha todos os campos obrigatórios', 'danger')
                return redirect(url_for('admin_editar_produto', id=id))
            
            if preco <= 0:
                flash('O preço deve ser maior que zero', 'danger')
                return redirect(url_for('admin_editar_produto', id=id))
            
            if estoque < 0:
                flash('O estoque não pode ser negativo', 'danger')
                return redirect(url_for('admin_editar_produto', id=id))
            
            # Atualizar produto
            conn.execute("""
                UPDATE produtos 
                SET nome = ?, descricao = ?, preco = ?, estoque = ?, categoria = ?
                WHERE id = ?
            """, (nome, descricao, preco, estoque, categoria if categoria else None, id))
            
            # Processar novas imagens
            if imagens and imagens[0].filename != '':
                # Remover imagens antigas
                imagens_antigas = conn.execute("""
                    SELECT imagem_path FROM produto_imagens WHERE produto_id = ?
                """, (id,)).fetchall()
                
                for img in imagens_antigas:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img['imagem_path']))
                    except Exception as e:
                        print(f"Erro ao remover imagem: {e}")
                
                conn.execute("DELETE FROM produto_imagens WHERE produto_id = ?", (id,))
                
                # Adicionar novas imagens
                for i, imagem in enumerate(imagens):
                    if imagem and allowed_file(imagem.filename):
                        filename = secure_filename(f"{id}_{i}.{imagem.filename.rsplit('.', 1)[1].lower()}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        imagem.save(filepath)
                        
                        # Definir imagem principal
                        is_principal = 1 if i == (imagem_principal or 0) else 0
                        conn.execute("""
                            INSERT INTO produto_imagens (produto_id, imagem_path, is_principal)
                            VALUES (?, ?, ?)
                        """, (id, filename, is_principal))
            
            # Atualizar imagem principal se necessário
            elif imagem_principal is not None:
                conn.execute("""
                    UPDATE produto_imagens 
                    SET is_principal = CASE 
                        WHEN id = ? THEN 1 
                        ELSE 0 
                    END
                    WHERE produto_id = ?
                """, (imagem_principal, id))
            
            conn.commit()
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('admin_produtos'))
        
        # Carregar imagens para edição
        imagens = conn.execute("""
            SELECT * FROM produto_imagens WHERE produto_id = ?
        """, (id,)).fetchall()
        
        return render_template('admin/editar_produto.html',
                             produto=produto,
                             imagens=imagens)
    except Exception as e:
        conn.rollback()
        print(f"Erro ao editar produto: {e}")
        flash('Erro ao editar produto', 'danger')
        return redirect(url_for('admin_editar_produto', id=id))
    finally:
        conn.close()

@app.route('/admin/produtos/excluir/<int:id>', methods=['POST'])
@admin_required
def admin_excluir_produto(id):
    """Exclusão de produtos"""
    conn = get_db_connection()
    try:
        # Obter imagens para excluir
        imagens = conn.execute("""
            SELECT imagem_path FROM produto_imagens WHERE produto_id = ?
        """, (id,)).fetchall()
        
        # Excluir do banco de dados
        conn.execute("DELETE FROM produto_imagens WHERE produto_id = ?", (id,))
        conn.execute("DELETE FROM produtos WHERE id = ?", (id,))
        conn.commit()
        
        # Excluir arquivos de imagem
        for img in imagens:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img['imagem_path']))
            except Exception as e:
                print(f"Erro ao excluir imagem: {e}")
        
        flash('Produto excluído com sucesso!', 'success')
        return redirect(url_for('admin_produtos'))
    except Exception as e:
        conn.rollback()
        print(f"Erro ao excluir produto: {e}")
        flash('Erro ao excluir produto', 'danger')
        return redirect(url_for('admin_produtos'))
    finally:
        conn.close()

@app.route('/admin/pedidos')
@admin_required
def admin_pedidos():
    """Listagem de pedidos para administradores"""
    busca = request.args.get('busca', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Itens por página

    conn = get_db_connection()
    
    # Query base
    query = """
        SELECT 
            p.id, 
            p.data_pedido, 
            p.total, 
            p.status,
            u.nome as usuario_nome,
            u.id as usuario_id
        FROM pedidos p
        LEFT JOIN usuarios u ON p.usuario_id = u.id
    """
    
    params = []
    
    # Filtro de busca
    if busca:
        query += " WHERE p.id LIKE ? OR u.nome LIKE ? OR p.status LIKE ?"
        search_term = f'%{busca}%'
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY p.data_pedido DESC"
    
    # Executar a query
    pedidos = conn.execute(query, params).fetchall()
    
    # Paginação
    total_pedidos = len(pedidos)
    total_pages = (total_pedidos + per_page - 1) // per_page
    
    # Aplicar paginação
    start = (page - 1) * per_page
    end = start + per_page
    pedidos_paginados = pedidos[start:end]
    
    conn.close()
    
    return render_template('admin/pedidos.html',
                         pedidos=pedidos_paginados,
                         pagination={
                             'page': page,
                             'per_page': per_page,
                             'total': total_pedidos,
                             'pages': total_pages,
                             'has_prev': page > 1,
                             'has_next': page < total_pages,
                             'prev_num': page - 1,
                             'next_num': page + 1
                         },
                         busca=busca)

@app.route('/admin/pedidos/<int:pedido_id>')
@admin_required
def admin_detalhes_pedido(pedido_id):
    """Detalhes de um pedido para administradores"""
    conn = get_db_connection()
    try:
        pedido = conn.execute("""
            SELECT p.*, u.nome as cliente, u.email
            FROM pedidos p
            JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.id = ?
        """, (pedido_id,)).fetchone()
        
        if not pedido:
            flash('Pedido não encontrado', 'danger')
            return redirect(url_for('admin_pedidos'))
        
        itens = conn.execute("""
            SELECT pi.*, p.nome, p.descricao, 
                   (pi.quantidade * pi.preco_unitario) as total_item,
                   img.imagem_path
            FROM pedido_itens pi
            JOIN produtos p ON pi.produto_id = p.id
            LEFT JOIN produto_imagens img ON p.id = img.produto_id AND img.is_principal = 1
            WHERE pi.pedido_id = ?
        """, (pedido_id,)).fetchall()
        
        return render_template('admin/detalhes_pedido.html',
                             pedido=pedido,
                             itens=itens)
    except Exception as e:
        print(f"Erro ao carregar pedido: {e}")
        flash('Erro ao carregar pedido', 'danger')
        return redirect(url_for('admin_pedidos'))
    finally:
        conn.close()

@app.route('/admin/pedidos/atualizar-status/<int:pedido_id>', methods=['POST'])
@admin_required
def admin_atualizar_status_pedido(pedido_id):
    """Atualiza o status de um pedido"""
    novo_status = request.form.get('status', '').strip()
    
    if novo_status not in ['pendente', 'processando', 'enviado', 'entregue', 'cancelado']:
        flash('Status inválido', 'danger')
        return redirect(url_for('admin_detalhes_pedido', pedido_id=pedido_id))
    
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE pedidos 
            SET status = ? 
            WHERE id = ?
        """, (novo_status, pedido_id))
        conn.commit()
        flash('Status do pedido atualizado!', 'success')
        return redirect(url_for('admin_detalhes_pedido', pedido_id=pedido_id))
    except Exception as e:
        conn.rollback()
        print(f"Erro ao atualizar status: {e}")
        flash('Erro ao atualizar status', 'danger')
        return redirect(url_for('admin_detalhes_pedido', pedido_id=pedido_id))
    finally:
        conn.close()

@app.route('/admin/usuarios')
@admin_required
def admin_usuarios():
    """Listagem de usuários para administradores"""
    conn = get_db_connection()
    try:
        busca = request.args.get('busca', '')
        
        query = "SELECT id, nome, email, banido, admin, data_cadastro FROM usuarios"
        params = []
        
        if busca:
            query += " WHERE nome LIKE ? OR email LIKE ?"
            params.extend([f'%{busca}%', f'%{busca}%'])
        
        query += " ORDER BY nome"
        
        usuarios = conn.execute(query, params).fetchall()
        return render_template('admin/usuarios.html', usuarios=usuarios, busca=busca)
    except Exception as e:
        print(f"Erro ao listar usuários: {e}")
        flash('Erro ao carregar usuários', 'danger')
        return render_template('admin/usuarios.html', usuarios=[])
    finally:
        conn.close()

@app.route('/admin/usuarios/<int:usuario_id>', methods=['GET', 'POST'])
@admin_required
def admin_editar_usuario(usuario_id):
    """Edição de usuários por administradores"""
    conn = get_db_connection()
    try:
        usuario = conn.execute("""
            SELECT id, nome, email, banido, admin 
            FROM usuarios 
            WHERE id = ?
        """, (usuario_id,)).fetchone()
        
        if not usuario:
            flash('Usuário não encontrado', 'danger')
            return redirect(url_for('admin_usuarios'))
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            banido = 1 if request.form.get('banido') == 'on' else 0
            admin = 1 if request.form.get('admin') == 'on' else 0
            nova_senha = request.form.get('nova_senha', '').strip()
            
            if not all([nome, email]):
                flash('Preencha todos os campos obrigatórios', 'danger')
                return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
            
            # Atualizar dados básicos
            conn.execute("""
                UPDATE usuarios 
                SET nome = ?, email = ?, banido = ?, admin = ?
                WHERE id = ?
            """, (nome, email, banido, admin, usuario_id))
            
            # Atualizar senha se fornecida
            if nova_senha:
                if len(nova_senha) < 6:
                    flash('A senha deve ter pelo menos 6 caracteres', 'danger')
                    return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
                
                conn.execute("""
                    UPDATE usuarios 
                    SET senha = ? 
                    WHERE id = ?
                """, (criar_hash(nova_senha), usuario_id))
            
            conn.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('admin_usuarios'))
        
        return render_template('admin/editar_usuario.html', usuario=usuario)
    except sqlite3.IntegrityError:
        conn.rollback()
        flash('Este email já está em uso', 'danger')
        return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
    except Exception as e:
        conn.rollback()
        print(f"Erro ao editar usuário: {e}")
        flash('Erro ao editar usuário', 'danger')
        return redirect(url_for('admin_editar_usuario', usuario_id=usuario_id))
    finally:
        conn.close()

# =============================================
# INICIALIZAÇÃO DO APLICATIVO
# =============================================

def verificar_estruturas():
    """Verifica e corrige estruturas do banco de dados"""
    conn = get_db_connection()
    try:
        # Verificar tabela produto_imagens
        colunas = conn.execute("PRAGMA table_info(produto_imagens)").fetchall()
        if not any(col['name'] == 'is_principal' for col in colunas):
            conn.execute("ALTER TABLE produto_imagens ADD COLUMN is_principal INTEGER DEFAULT 0")
            print("Coluna is_principal adicionada à produto_imagens")
        
        # Verificar tabela carrinho
        colunas = conn.execute("PRAGMA table_info(carrinho)").fetchall()
        if not any(col['name'] == 'id' for col in colunas):
            conn.execute("ALTER TABLE carrinho ADD COLUMN id INTEGER PRIMARY KEY AUTOINCREMENT")
            print("Coluna id adicionada ao carrinho")
        
        conn.commit()
    except Exception as e:
        print(f"Erro ao verificar estruturas: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    # Criar pastas necessárias
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists('static/js'):
        os.makedirs('static/js')
    
    # Banco de dados
    init_db()
    atualizar_banco_dados()
    verificar_estruturas()
    
    # Verificar se o main.js existe
    if not os.path.exists('static/js/main.js'):
        with open('static/js/main.js', 'w') as f:
            f.write('// Arquivo JavaScript inicial\nconsole.log("Aplicação carregada")')
    
    app.run(debug=True)