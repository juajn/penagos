import cv2
import numpy as np
from paddleocr import PaddleOCR
import re
import logging

logger = logging.getLogger(__name__)

def extraer_filas_columnas(imagen_path):
    """
    Extrae filas y columnas de una imagen tabular
    """
    try:
        # Inicializar OCR
        ocr = PaddleOCR(use_angle_cls=True, lang='es')
        
        # Leer imagen
        imagen = cv2.imread(imagen_path)
        if imagen is None:
            raise ValueError("No se pudo cargar la imagen")
        
        # Ejecutar OCR
        resultado = ocr.ocr(imagen, cls=True)
        
        if not resultado or not resultado[0]:
            return []
        
        # Extraer texto y coordenadas
        elementos = []
        for linea in resultado[0]:
            bbox, (texto, confianza) = linea
            if confianza > 0.5:  # Filtrar por confianza
                # Calcular posición promedio
                x = sum([punto[0] for punto in bbox]) / 4
                y = sum([punto[1] for punto in bbox]) / 4
                elementos.append({
                    'texto': texto.strip(),
                    'x': x,
                    'y': y,
                    'confianza': confianza
                })
        
        return elementos
    
    except Exception as e:
        logger.error(f"Error en extraer_filas_columnas: {str(e)}")
        return []

def procesar_imagen_tabular(imagen_path):
    """
    Procesa una imagen tabular y extrae registros estructurados
    """
    try:
        elementos = extraer_filas_columnas(imagen_path)
        
        if not elementos:
            return []
        
        # Ordenar elementos por posición Y (filas) y luego por X (columnas)
        elementos.sort(key=lambda x: (x['y'], x['x']))
        
        # Agrupar por filas (elementos con Y similares)
        filas = []
        fila_actual = []
        y_anterior = None
        tolerancia_y = 20  # Tolerancia para considerar elementos en la misma fila
        
        for elemento in elementos:
            if y_anterior is None or abs(elemento['y'] - y_anterior) < tolerancia_y:
                fila_actual.append(elemento)
            else:
                if fila_actual:
                    filas.append(sorted(fila_actual, key=lambda x: x['x']))
                fila_actual = [elemento]
            y_anterior = elemento['y']
        
        # Agregar la última fila
        if fila_actual:
            filas.append(sorted(fila_actual, key=lambda x: x['x']))
        
        # Convertir filas a registros estructurados
        registros = []
        
        for fila in filas[1:]:  # Saltar la primera fila (encabezados)
            if len(fila) >= 3:  # Mínimo 3 columnas para considerar válida
                registro = {
                    'hora_inicio': limpiar_hora(fila[0]['texto'] if len(fila) > 0 else ''),
                    'hora_final': limpiar_hora(fila[1]['texto'] if len(fila) > 1 else ''),
                    'codigo_actividad': limpiar_texto(fila[2]['texto'] if len(fila) > 2 else ''),
                    'unidad_produccion': limpiar_texto(fila[3]['texto'] if len(fila) > 3 else ''),
                    'codigo_equipo': limpiar_texto(fila[4]['texto'] if len(fila) > 4 else ''),
                    'referencia_producto': limpiar_texto(fila[5]['texto'] if len(fila) > 5 else ''),
                    'cantidad_trabajada': extraer_numero(fila[6]['texto'] if len(fila) > 6 else '0'),
                    'observaciones': limpiar_texto(fila[7]['texto'] if len(fila) > 7 else ''),
                }
                
                # Solo agregar si tiene datos válidos
                if any(v for v in registro.values() if str(v).strip()):
                    registros.append(registro)
        
        return registros
    
    except Exception as e:
        logger.error(f"Error en procesar_imagen_tabular: {str(e)}")
        return []

def limpiar_hora(texto):
    """
    Limpia y valida formato de hora
    """
    try:
        # Buscar patrón HH:MM
        patron = re.search(r'(\d{1,2}):(\d{2})', texto)
        if patron:
            horas = int(patron.group(1))
            minutos = int(patron.group(2))
            if 0 <= horas <= 23 and 0 <= minutos <= 59:
                return f"{horas:02d}:{minutos:02d}"
        
        # Buscar solo números y asumir formato HHMM
        numeros = re.findall(r'\d+', texto)
        if numeros:
            num_str = numeros[0]
            if len(num_str) >= 3:
                if len(num_str) == 3:  # Formato HMM
                    horas = int(num_str[0])
                    minutos = int(num_str[1:3])
                elif len(num_str) == 4:  # Formato HHMM
                    horas = int(num_str[0:2])
                    minutos = int(num_str[2:4])
                else:
                    return "00:00"
                
                if 0 <= horas <= 23 and 0 <= minutos <= 59:
                    return f"{horas:02d}:{minutos:02d}"
        
        return "00:00"
    except:
        return "00:00"

def limpiar_texto(texto):
    """
    Limpia texto eliminando caracteres extraños
    """
    if not texto:
        return ""
    
    # Remover caracteres especiales pero mantener espacios, números y letras
    texto_limpio = re.sub(r'[^\w\s\-.]', '', texto)
    return texto_limpio.strip()

def extraer_numero(texto):
    """
    Extrae número entero del texto
    """
    try:
        # Buscar números en el texto
        numeros = re.findall(r'\d+', str(texto))
        if numeros:
            return int(numeros[0])
        return 0
    except:
        return 0