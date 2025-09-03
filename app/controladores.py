import traceback
import cv2
import os
import logging
import numpy as np
from flask import Blueprint, jsonify, render_template, request, redirect, session, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func
from datetime import date, datetime, timedelta
from paddleocr import PaddleOCR

from extensions import db, login_manager, bcrypt
from app.models import Usuario, Actividad
from app.servicios.ocr_servicio import extraer_filas_columnas, procesar_imagen_tabular

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------
# BLUEPRINTS
# ---------------------

auth_bp = Blueprint('auth', __name__)
admin_bp = Blueprint('admin', __name__)
analista_bp = Blueprint('analista', __name__)
operario_bp = Blueprint('operario', __name__)
api_bp = Blueprint('api', __name__)
controller_bp = Blueprint('controller', __name__)
# ---------------------
# FLASK-LOGIN
# ---------------------
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ---------------------
# AUTENTICACIÓN
# ---------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        documento = request.form['documento']
        contraseña = request.form['contraseña']

        usuario = Usuario.query.filter_by(documento=documento).first()

        if usuario and bcrypt.check_password_hash(usuario.contraseña, contraseña):
            login_user(usuario)

            if usuario.rol == 'Admin':
                return redirect(url_for('admin.dashboard_admin'))
            elif usuario.rol == 'Analista':
                return redirect(url_for('analista.dashboard_analista'))
            elif usuario.rol == 'Operario':
                flash("El rol Operario no tiene permitido acceder al sistema", "danger")
                return redirect(url_for('auth.login'))
            else:
                abort(403)  
        else:
            flash("Documento o contraseña incorrectos", "danger")
            return redirect(url_for('auth.login'))
        
        
    return render_template('auth/login.html')

@auth_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre_completo = request.form.get('nombre_completo')
        documento = request.form.get('documento')
        contraseña = request.form.get('contraseña')
        rol = request.form.get('rol')  # viene directamente del formulario

        if not all([nombre_completo, documento, contraseña, rol]):
            flash("Todos los campos son obligatorios", "danger")
            return redirect(url_for('auth.registro'))

        if Usuario.query.filter_by(documento=documento).first():
            flash("Este documento ya está registrado", "danger")
            return redirect(url_for('auth.registro'))

        if rol not in ['Admin', 'Analista', 'Operario']:
            flash("Rol no válido", "danger")
            return redirect(url_for('auth.registro'))

        try:
            hashed_password = bcrypt.generate_password_hash(contraseña).decode('utf-8')
            nuevo_usuario = Usuario(
                nombre_completo=nombre_completo,
                documento=documento,
                contraseña=hashed_password,
                rol=rol
            )
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash("Usuario registrado correctamente. Por favor inicie sesión.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al registrar usuario: {str(e)}")
            flash("Error al registrar el usuario", "danger")

    # Roles fijos para el formulario
    roles = ['Admin', 'Analista', 'Operario']
    return render_template('auth/register.html', roles=roles)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente", "info")
    return redirect(url_for('auth.login'))
# ---------------------
# ADMIN
# ---------------------
@admin_bp.route('/dashboard')
@login_required
def dashboard_admin():
    if current_user.rol != 'Admin':
        abort(403)

    total_usuarios = Usuario.query.count()
    total_actividades = Actividad.query.count()
    
    # Obtener parámetros de filtro de fechas (si existen)
    fecha_inicio = request.args.get('fecha_inicio', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    fecha_fin = request.args.get('fecha_fin', datetime.now().strftime('%Y-%m-%d'))
    
    # Convertir a objetos datetime para la consulta
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
    except ValueError:
        # Si hay error en el formato, usar valores por defecto
        fecha_inicio_dt = datetime.now() - timedelta(days=7)
        fecha_fin_dt = datetime.now()
        fecha_inicio = fecha_inicio_dt.strftime('%Y-%m-%d')
        fecha_fin = fecha_fin_dt.strftime('%Y-%m-%d')
    
    # Asegurarse de que fecha_fin incluya todo el día
    fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
    
    # Obtener actividades dentro del rango de fechas para la gráfica
    actividades_filtradas = Actividad.query.filter(
        Actividad.fecha >= fecha_inicio_dt,
        Actividad.fecha <= fecha_fin_dt
    ).order_by(Actividad.fecha.asc()).all()
    
    # Preparar datos para la gráfica de actividades por fecha
    actividades_por_fecha = {}
    for actividad in actividades_filtradas:
        fecha_str = actividad.fecha.strftime('%Y-%m-%d')
        actividades_por_fecha[fecha_str] = actividades_por_fecha.get(fecha_str, 0) + 1
    
    # Ordenar fechas y obtener datos para la gráfica
    fechas_ordenadas = sorted(actividades_por_fecha.keys())
    conteo_actividades = [actividades_por_fecha[fecha] for fecha in fechas_ordenadas]
    
    # Obtener conteo de usuarios por rol
    admin_count = Usuario.query.filter_by(rol='Admin').count()
    analista_count = Usuario.query.filter_by(rol='Analista').count()
    operario_count = Usuario.query.filter_by(rol='Operario').count()
    roles_conteo = [admin_count, analista_count, operario_count]
    
    # Obtener la fecha de la última actividad
    ultima_actividad = Actividad.query.order_by(Actividad.fecha.desc()).first()
    ultima_fecha = ultima_actividad.fecha.strftime('%Y-%m-%d %H:%M') if ultima_actividad else "N/A"
    
    # Obtener todas las actividades recientes (sin filtro para la tabla)
    actividades_recientes = Actividad.query.order_by(Actividad.fecha.desc()).limit(5).all()
    
    # Obtener todos los usuarios (para el modal)
    usuarios = Usuario.query.all()

    return render_template('admin/dashboard_admin.html',
                           total_usuarios=total_usuarios,
                           total_actividades=total_actividades,
                           actividades_recientes=actividades_recientes,
                           fechas_labels=fechas_ordenadas,
                           actividades_data=conteo_actividades,
                           roles_conteo=roles_conteo,
                           ultima_fecha=ultima_fecha,
                           usuarios=usuarios,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)

from datetime import datetime

@admin_bp.route('/actividades')
@login_required
def actividades():
    if current_user.rol != 'Admin':
        abort(403)
    
    # Obtener parámetros de filtro
    texto = request.args.get('texto', '')
    turno = request.args.get('turno', '')
    usuario_id = request.args.get('usuario_id', '')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    # Construir consulta base
    query = Actividad.query
    
    # Aplicar filtros
    if texto:
        query = query.filter(
            (Actividad.codigo_actividad.ilike(f'%{texto}%')) |
            (Actividad.descripcion_actividad.ilike(f'%{texto}%')) |
            (Actividad.referencia_producto.ilike(f'%{texto}%'))
        )
    
    if turno:
        query = query.filter(Actividad.turno == turno)
    
    if usuario_id:
        query = query.filter(Actividad.usuario_id == usuario_id)
    
    if fecha_inicio:
        query = query.filter(Actividad.fecha >= fecha_inicio)
    
    if fecha_fin:
        query = query.filter(Actividad.fecha <= fecha_fin)
    
    # Obtener actividades y usuarios
    actividades = query.order_by(Actividad.fecha.desc(), Actividad.hora_inicio.desc()).all()
    usuarios = Usuario.query.all()
    
    # Obtener fecha de hoy para el filtro
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('admin/trabajos/index.html',
                         actividades=actividades,
                         usuarios=usuarios,
                         hoy=hoy,
                         ultima_actualizacion=datetime.now().strftime('%H:%M'),
                         filtros={
                             'texto': texto,
                             'turno': turno,
                             'usuario_id': usuario_id,
                             'fecha_inicio': fecha_inicio,
                             'fecha_fin': fecha_fin
                         })
# 🔹 Crear actividad
@admin_bp.route("/crear_actividad", methods=["POST"])
def crear_actividad():
    try:
        nueva = Actividad(
            fecha=request.form.get("fecha"),
            turno=request.form.get("turno"),
            hora_inicio=request.form.get("hora_inicio"),
            hora_final=request.form.get("hora_final"),
            codigo_actividad=request.form.get("codigo_actividad"),
            descripcion_actividad=request.form.get("descripcion_actividad"),
            codigo_equipo=request.form.get("codigo_equipo"),
            orden_produccion=request.form.get("orden_produccion"),
            referencia_producto=request.form.get("referencia_producto"),
            cantidad_trabajada=request.form.get("cantidad_trabajada"),
            usuario_id=request.form.get("usuario_id"),
            observaciones=request.form.get("observaciones")
        )
        db.session.add(nueva)
        db.session.commit()
        flash("Actividad creada correctamente ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al crear la actividad ❌: {e}", "danger")

    return redirect(url_for("admin.actividades"))


# 🔹 Editar actividad
@admin_bp.route("/editar_actividad/<int:id>", methods=["POST"])
def editar_actividad(id):
    actividad = Actividad.query.get_or_404(id)
    try:
        actividad.fecha = request.form.get("fecha")
        actividad.turno = request.form.get("turno")
        actividad.hora_inicio = request.form.get("hora_inicio")
        actividad.hora_final = request.form.get("hora_final")
        actividad.codigo_actividad = request.form.get("codigo_actividad")
        actividad.descripcion_actividad = request.form.get("descripcion_actividad")
        actividad.codigo_equipo = request.form.get("codigo_equipo")
        actividad.orden_produccion = request.form.get("orden_produccion")
        actividad.referencia_producto = request.form.get("referencia_producto")
        actividad.cantidad_trabajada = request.form.get("cantidad_trabajada")
        actividad.usuario_id = request.form.get("usuario_id")
        actividad.observaciones = request.form.get("observaciones")

        db.session.commit()
        flash("Actividad actualizada correctamente ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al editar la actividad ❌: {e}", "danger")

    return redirect(url_for("admin.actividades"))


# 🔹 Eliminar actividad
@admin_bp.route("/eliminar_actividad/<int:id>", methods=["POST"])
def eliminar_actividad(id):
    actividad = Actividad.query.get_or_404(id)
    try:
        db.session.delete(actividad)
        db.session.commit()
        flash("Actividad eliminada correctamente ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar la actividad ❌: {e}", "danger")

    return redirect(url_for("admin.actividades"))
@admin_bp.route('/usuarios')
@login_required
def gestion_usuarios():
    query = request.args.get('q', '')

    if query:
        usuarios = Usuario.query.filter(
            (Usuario.documento.like(f"%{query}%")) | 
            (Usuario.nombre_completo.like(f"%{query}%"))
        ).all()
    else:
        usuarios = Usuario.query.all()

    return render_template('admin/usuarios/gestion_usuarios.html', usuarios=usuarios)

# Crear usuario
@admin_bp.route('/usuario/nuevo', methods=['POST'])
@login_required
def nuevo_usuario():
    nombre = request.form['nombre']
    documento = request.form['documento']
    contraseña = request.form['contraseña']
    rol = request.form['rol']

    # ✅ CORRECCIÓN: Usar bcrypt consistentemente
    hashed_password = bcrypt.generate_password_hash(contraseña).decode('utf-8')
    
    nuevo_usuario = Usuario(
        nombre_completo=nombre,
        documento=documento,
        contraseña=hashed_password,
        rol=rol,
    )
    
    try:
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash('Usuario creado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al crear usuario: {str(e)}")
        flash('Error al crear el usuario.', 'danger')

    return redirect(url_for('admin.gestion_usuarios'))
# Editar usuario
@admin_bp.route('/usuario/<int:id>/editar', methods=['POST'])
@login_required
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)

    usuario.nombre_completo = request.form['nombre']
    usuario.documento = request.form['documento']
    usuario.rol = request.form['rol']

    db.session.commit()
    flash('Usuario actualizado correctamente.', 'success')
    return redirect(url_for('admin.gestion_usuarios'))

# Eliminar usuario
@admin_bp.route('/usuario/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_usuario(id):
    usuario = Usuario.query.get_or_404(id)

    try:
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuario eliminado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al eliminar usuario: ' + str(e), 'danger')

    return redirect(url_for('admin.gestion_usuarios'))
# ---------------------
# ANALISTA
# ---------------------
@analista_bp.route('/dashboard')
@login_required
def dashboard_analista():
    # Obtener parámetros de filtro
    busqueda = request.args.get('busqueda', '')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    fecha_inicio_grafica = request.args.get('fecha_inicio_grafica', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    fecha_fin_grafica = request.args.get('fecha_fin_grafica', datetime.now().strftime('%Y-%m-%d'))
    agrupacion = request.args.get('agrupacion', 'dia')

    # Construir consulta base para actividades
    query = Actividad.query

    # Aplicar filtros de búsqueda
    if busqueda:
        query = query.join(Usuario).filter(
            (Usuario.nombre_completo.ilike(f'%{busqueda}%')) | 
            (Usuario.documento.ilike(f'%{busqueda}%'))
        )

    # Aplicar filtros de fecha
    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query = query.filter(Actividad.fecha >= fecha_inicio_dt)
        except ValueError:
            pass

    if fecha_fin:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            query = query.filter(Actividad.fecha <= fecha_fin_dt)
        except ValueError:
            pass

    # Obtener actividades filtradas
    actividades = query.order_by(Actividad.fecha.desc()).all()

    # Calcular estadísticas básicas
    hoy = datetime.now().date()
    total_cantidad = sum(act.cantidad_trabajada for act in actividades if act.cantidad_trabajada)
    
    # Operarios únicos (solo rol Operario)
    operarios_unicos = list(set(act.usuario for act in actividades if act.usuario.rol == 'Operario'))
    
    # Preparar datos para las gráficas
    datos_graficas = obtener_datos_graficas(fecha_inicio_grafica, fecha_fin_grafica, agrupacion)

    return render_template('analista/dashboard_analista.html',
                         actividades=actividades,
                         datos_graficas=datos_graficas,
                         fecha_inicio_default=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                         fecha_fin_default=datetime.now().strftime('%Y-%m-%d'),
                         hoy=hoy,
                         total_cantidad=total_cantidad,
                         operarios_unicos=operarios_unicos,
                         now=datetime.now())


def obtener_datos_graficas(fecha_inicio, fecha_fin, agrupacion):
    """Obtiene datos para las gráficas basado en los filtros"""
    try:
        # Convertir fechas a objetos datetime
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        
        # Consulta base para el período seleccionado
        query = Actividad.query.filter(
            Actividad.fecha.between(fecha_inicio_dt, fecha_fin_dt)
        )
        
        actividades_periodo = query.all()
        
        # Datos para gráfica de actividades por fecha
        if agrupacion == 'dia':
            fechas = [act.fecha.strftime('%Y-%m-%d') for act in actividades_periodo]
        elif agrupacion == 'semana':
            fechas = [f"Semana {act.fecha.isocalendar()[1]}-{act.fecha.year}" for act in actividades_periodo]
        else:  # mes
            fechas = [act.fecha.strftime('%Y-%m') for act in actividades_periodo]
        
        # Contar actividades por grupo
        from collections import defaultdict
        actividades_por_grupo = defaultdict(int)
        for i, fecha in enumerate(fechas):
            actividades_por_grupo[fecha] += 1
        
        # Datos para gráfica de turnos
        turnos_count = {'Mañana': 0, 'Tarde': 0, 'Noche': 0}
        for act in actividades_periodo:
            if act.turno in turnos_count:
                turnos_count[act.turno] += 1
        
        # Top 5 operarios
        from collections import Counter
        operarios_count = Counter()
        for act in actividades_periodo:
            if act.usuario.rol == 'Operario':
                operarios_count[act.usuario.nombre_completo] += 1
        
        top_operarios = operarios_count.most_common(5)
        
        # Producción acumulada
        produccion_acumulada = []
        acumulado = 0
        fechas_unicas = sorted(set(fechas))
        
        for fecha in fechas_unicas:
            if agrupacion == 'dia':
                actividades_fecha = [act for act in actividades_periodo if act.fecha.strftime('%Y-%m-%d') == fecha]
            elif agrupacion == 'semana':
                semana, year = fecha.split('-')
                actividades_fecha = [act for act in actividades_periodo 
                                   if f"Semana {act.fecha.isocalendar()[1]}-{act.fecha.year}" == fecha]
            else:
                actividades_fecha = [act for act in actividades_periodo 
                                   if act.fecha.strftime('%Y-%m') == fecha]
            
            acumulado += sum(act.cantidad_trabajada for act in actividades_fecha if act.cantidad_trabajada)
            produccion_acumulada.append(acumulado)
        
        return {
            'fechas': list(actividades_por_grupo.keys()),
            'cantidades': list(actividades_por_grupo.values()),
            'turnos': [turnos_count['Mañana'], turnos_count['Tarde'], turnos_count['Noche']],
            'top_operarios_nombres': [op[0] for op in top_operarios],
            'top_operarios_cantidades': [op[1] for op in top_operarios],
            'produccion_acumulada': produccion_acumulada
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo datos para gráficas: {str(e)}")
        # Retornar datos vacíos en caso de error
        return {
            'fechas': [],
            'cantidades': [],
            'turnos': [0, 0, 0],
            'top_operarios_nombres': [],
            'top_operarios_cantidades': [],
            'produccion_acumulada': []
        }


@analista_bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_actividad():
    if request.method == 'POST':
        try:
            # Validar que el usuario seleccionado sea un operario
            usuario_id = request.form.get('usuario_id')
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.rol != 'Operario':
                flash("Debe seleccionar un operario válido", "danger")
                return redirect(url_for('analista.crear_actividad'))
            
            actividad = Actividad(
                usuario_id=usuario_id,
                fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date(),
                turno=request.form.get('turno'),
                hora_inicio=datetime.strptime(request.form.get('hora_inicio'), '%H:%M').time(),
                hora_final=datetime.strptime(request.form.get('hora_final'), '%H:%M').time(),
                codigo_equipo=request.form.get('codigo_equipo'),
                codigo_actividad=request.form.get('codigo_actividad'),
                orden_produccion=request.form.get('orden_produccion'),
                referencia_producto=request.form.get('referencia_producto'),
                descripcion_actividad=request.form.get('descripcion_actividad'),
                cantidad_trabajada=int(request.form.get('cantidad_trabajada', 0)),
                observaciones=request.form.get('observaciones', '')
            )
            db.session.add(actividad)
            db.session.commit()
            flash("Actividad registrada correctamente", "success")
            return redirect(url_for('analista.dashboard_analista'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al crear actividad: {str(e)}")
            flash("Error al registrar la actividad", "danger")

    # Solo mostrar usuarios con rol Operario
    usuarios = Usuario.query.filter_by(rol='Operario').all()
    return render_template('analista/nuevo_trabajo.html',
                         usuarios=usuarios,
                         now=datetime.now())


@analista_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_actividad(id):
    actividad = Actividad.query.get_or_404(id)

    if request.method == 'POST':
        try:
            # Validar que el usuario seleccionado sea un operario
            usuario_id = request.form.get('usuario_id')
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.rol != 'Operario':
                flash("Debe seleccionar un operario válido", "danger")
                return redirect(url_for('analista.editar_actividad', id=id))
            
            actividad.usuario_id = usuario_id
            actividad.fecha = datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date()
            actividad.turno = request.form.get('turno')
            actividad.hora_inicio = datetime.strptime(request.form.get('hora_inicio'), '%H:%M').time()
            actividad.hora_final = datetime.strptime(request.form.get('hora_final'), '%H:%M').time()
            actividad.codigo_equipo = request.form.get('codigo_equipo')
            actividad.codigo_actividad = request.form.get('codigo_actividad')
            actividad.orden_produccion = request.form.get('orden_produccion')
            actividad.referencia_producto = request.form.get('referencia_producto')
            actividad.descripcion_actividad = request.form.get('descripcion_actividad')
            actividad.cantidad_trabajada = int(request.form.get('cantidad_trabajada', 0))
            actividad.observaciones = request.form.get('observaciones', '')
            
            db.session.commit()
            flash("Actividad actualizada correctamente", "success")
            return redirect(url_for('analista.dashboard_analista'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al editar actividad: {str(e)}")
            flash("Error al actualizar la actividad", "danger")

    # Solo mostrar usuarios con rol Operario
    usuarios = Usuario.query.filter_by(rol='Operario').all()
    return render_template('analista/nuevo_trabajo.html',
                         actividad=actividad,
                         usuarios=usuarios,
                         now=datetime.now())


@analista_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_actividad(id):
    actividad = Actividad.query.get_or_404(id)
    try:
        db.session.delete(actividad)
        db.session.commit()
        flash("Actividad eliminada correctamente", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al eliminar actividad: {str(e)}")
        flash("Error al eliminar la actividad", "danger")
    
    return redirect(url_for('analista.dashboard_analista'))

# ---------------------
# OPERARIO
# ---------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'app', 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@operario_bp.route('/procesar_imagen', methods=['POST'])
@login_required
def procesar_imagen():
    

    if 'imagen' not in request.files:
        flash('No se proporcionó ninguna imagen', 'danger')
        return redirect(url_for('operario.dashboard_operario'))

    archivo = request.files['imagen']
    if archivo.filename == '':
        flash('No se seleccionó ningún archivo', 'danger')
        return redirect(url_for('operario.dashboard_operario'))

    try:
        # Guardar imagen temporalmente
        nombre_archivo = secure_filename(archivo.filename)
        ruta_temporal = os.path.join(UPLOAD_FOLDER, nombre_archivo)
        archivo.save(ruta_temporal)

        # Verificar que es una imagen válida
        img = cv2.imread(ruta_temporal)
        if img is None:
            flash('El archivo no es una imagen válida', 'danger')
            return redirect(url_for('operario.dashboard_operario'))

        # Procesar imagen
        registros = procesar_imagen_tabular(ruta_temporal)
        
        if not registros:
            flash('No se detectaron datos en la imagen. Asegúrese que la tabla es clara y está bien alineada.', 'warning')
            return redirect(url_for('operario.dashboard_operario'))
        
        # Guardar en base de datos
        registros_guardados = 0
        for registro in registros:
            try:
                actividad = Actividad(
                    fecha=date.today(),
                    turno='Mañana',
                    hora_inicio=registro.get('hora_inicio', '00:00'),
                    hora_final=registro.get('hora_final', '00:00'),
                    codigo_actividad=registro.get('actividad_parada', ''),
                    descripcion_actividad=registro.get('unidad_produccion', ''),
                    codigo_equipo=registro.get('codigo_equipo', ''),
                    orden_produccion=registro.get('referencia_producto', ''),
                    cantidad_trabajada=int(registro.get('cantidad_trabajada', 0)),
                    observaciones=registro.get('observaciones', ''),
                    usuario_id=current_user.id
                )
                db.session.add(actividad)
                registros_guardados += 1
            except Exception as e:
                logger.error(f"Error procesando registro: {str(e)}")
                continue
        
        db.session.commit()
        flash(f'Se registraron {registros_guardados} actividades correctamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en procesar_imagen: {str(e)}")
        flash(f'Error al procesar la imagen: {str(e)}', 'danger')
    finally:
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)

    return redirect(url_for('operario.dashboard_operario'))

@operario_bp.route('/verificar-ocr', methods=['POST'])
@login_required
def verificar_ocr():
   

    registros = []
    errores = []
    num_filas = len(request.form.getlist('hora_inicio'))

    for i in range(num_filas):
        try:
            cantidad_valor = request.form.getlist('cantidad')[i].strip()
            if not cantidad_valor.isdigit():
                raise ValueError("La cantidad debe ser un número")

            registros.append({
                'hora_inicio': request.form.getlist('hora_inicio')[i],
                'hora_final': request.form.getlist('hora_final')[i],
                'codigo_actividad': request.form.getlist('codigo_actividad')[i],
                'descripcion': request.form.getlist('descripcion')[i],
                'codigo_equipo': request.form.getlist('codigo_equipo')[i],
                'orden_produccion': request.form.getlist('orden_produccion')[i],
                'referencia_producto': request.form.getlist('referencia_producto')[i],
                'cantidad': int(cantidad_valor),
                'observaciones': request.form.getlist('observaciones')[i],
            })
        except ValueError as e:
            errores.append(f"Fila {i+1}: {str(e)}")

    if errores:
        for error in errores:
            flash(error, "danger")
        return redirect(url_for('operario.dashboard_operario'))

    try:
        for reg in registros:
            actividad = Actividad(
                usuario_id=current_user.id,
                fecha=date.today(),
                turno='Mañana',
                hora_inicio=reg['hora_inicio'],
                hora_final=reg['hora_final'],
                codigo_actividad=reg['codigo_actividad'],
                descripcion_actividad=reg['descripcion'],
                codigo_equipo=reg['codigo_equipo'],
                orden_produccion=reg['orden_produccion'],
                referencia_producto=reg['referencia_producto'],
                cantidad_trabajada=reg['cantidad'],
                observaciones=reg['observaciones'],
            )
            db.session.add(actividad)

        db.session.commit()
        flash("Actividades registradas exitosamente", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al guardar actividades: {str(e)}")
        flash("Error al guardar las actividades", "danger")

    return redirect(url_for('operario.dashboard_operario'))

# ---------------------
# API
# ---------------------
@api_bp.route('/actividades/filtrar')
def filtrar_actividades():
    inicio = request.args.get('inicio')
    fin = request.args.get('fin')

    query = db.session.query(Actividad.fecha, func.count().label('conteo'))\
                     .group_by(Actividad.fecha)

    if inicio and fin:
        try:
            inicio_date = datetime.strptime(inicio, '%Y-%m-%d').date()
            fin_date = datetime.strptime(fin, '%Y-%m-%d').date()
            query = query.filter(Actividad.fecha.between(inicio_date, fin_date))
        except ValueError:
            return jsonify({'error': 'Formato de fecha inválido'}), 400

    resultados = query.order_by(Actividad.fecha).all()
    fechas = [r.fecha.strftime('%Y-%m-%d') for r in resultados]
    conteos = [r.conteo for r in resultados]

    return jsonify({'fechas': fechas, 'conteos': conteos})

# ---------------------
# CONTROLADOR GENERAL
# ---------------------
@controller_bp.route('/registrar_actividad', methods=['POST'])
@login_required
def registrar_actividad():
    try:
        actividad = Actividad(
            usuario_id=int(request.form.get('usuario_id')),
            fecha=datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date(),
            turno=request.form.get('turno'),
            hora_inicio=datetime.strptime(request.form.get('hora_inicio'), '%H:%M').time(),
            hora_final=datetime.strptime(request.form.get('hora_final'), '%H:%M').time(),
            codigo_equipo=request.form.get('codigo_equipo'),
            codigo_actividad=request.form.get('codigo_actividad'),
            orden_produccion=request.form.get('orden_produccion'),
            referencia_producto=request.form.get('referencia_producto'),
            descripcion_actividad=request.form.get('descripcion_actividad'),
            cantidad_trabajada=int(request.form.get('cantidad_trabajada', 0)),
            observaciones=request.form.get('observaciones', '')
        )

        db.session.add(actividad)
        db.session.commit()
        flash('Actividad registrada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al registrar actividad: {str(e)}")
        flash(f'Error al registrar la actividad: {str(e)}', 'danger')

    return redirect(url_for('controller.vista_actividad'))

@controller_bp.route('/actividad')
@login_required
def vista_actividad():
    actividades = Actividad.query.order_by(Actividad.fecha.desc()).all()
    return render_template('actividad/listar.html', actividades=actividades)