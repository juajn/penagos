from flask import Flask, redirect
from extensions import db, login_manager, bcrypt
from config import Config
import os
from app.controladores import auth_bp, admin_bp, analista_bp, operario_bp, api_bp, controller_bp

def crear_aplicacion():
    app = Flask(__name__, template_folder=os.path.join('app', 'templates'))
    app.config.from_object(Config)

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # User loader para Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Usuario
        return Usuario.query.get(int(user_id))

    with app.app_context():
        # Crear tablas existentes en models.py (usuarios, actividades)
        db.create_all()

        # Registrar Blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(analista_bp, url_prefix='/analista')
        app.register_blueprint(operario_bp, url_prefix='/operario')
        app.register_blueprint(api_bp, url_prefix='/api')
        app.register_blueprint(controller_bp, url_prefix='/controller')
    @app.route('/')
    def inicio():
        return redirect('/login')

    return app

if __name__ == '__main__':
    app = crear_aplicacion()
    app.run(debug=True)
