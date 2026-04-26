import streamlit as st
import pandas as pd
import googlemaps
from google import genai
import requests
from io import BytesIO
import time
import base64
from PIL import Image

# Configuración de la página
st.set_page_config(page_title="Máquina de Prospección IA", page_icon="🤖", layout="wide")

# Título y descripción
st.title("🤖 Máquina Automática de Prospección con IA")
st.markdown("Encuentra negocios, evalúa sus páginas web con Inteligencia Artificial y genera correos de ventas personalizados en minutos.")

# --- BARRA LATERAL: CONFIGURACIÓN ---
st.sidebar.header("🔑 Configuración de APIs")
st.sidebar.markdown("Ingresa tus claves para que el sistema funcione.")
gmaps_api_key = st.sidebar.text_input("Google Maps API Key", type="password")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Parámetros de Búsqueda")
search_query = st.sidebar.text_input("¿Qué buscas?", value="Estéticas en Polanco, CDMX")
max_results = st.sidebar.slider("Límite de negocios a analizar", min_value=1, max_value=20, value=5)

# --- FUNCIONES CORE ---

def get_places(query, api_key, max_results=5):
    """Obtiene los lugares usando Google Maps API."""
    gmaps = googlemaps.Client(key=api_key)
    try:
        places_result = gmaps.places(query=query)
        results = []
        for place in places_result.get('results', [])[:max_results]:
            place_id = place['place_id']
            # Obtener detalles completos para sacar el website y email si existe
            details = gmaps.place(place_id, fields=['name', 'website', 'formatted_phone_number', 'rating'])['result']
            
            results.append({
                "Nombre": details.get('name', 'N/A'),
                "Teléfono": details.get('formatted_phone_number', 'N/A'),
                "Website": details.get('website', 'No tiene'),
                "Rating": details.get('rating', 'N/A')
            })
        return results
    except Exception as e:
        st.error(f"Error en Google Maps API: {e}")
        return []

def get_website_screenshot(url):
    """Obtiene una captura de pantalla de la URL usando la API gratuita de Microlink."""
    if url == 'No tiene':
        return None
    try:
        # Microlink API gratuita para tomar screenshot
        api_url = f"https://api.microlink.io?url={url}&screenshot=true&meta=false"
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            screenshot_url = data.get('data', {}).get('screenshot', {}).get('url')
            if screenshot_url:
                img_response = requests.get(screenshot_url)
                img = Image.open(BytesIO(img_response.content))
                return img
    except Exception as e:
        st.warning(f"No se pudo tomar captura de {url}: {e}")
    return None

def evaluate_website_and_write_email(img, website_url, business_name, gemini_key):
    """Usa Gemini para evaluar la imagen y redactar el correo."""
    try:
        client = genai.Client(api_key=gemini_key)
        
        # 1. Evaluación Visual
        prompt_eval = (
            "Eres un experto diseñador web. Revisa la captura de pantalla de esta página web. "
            "Evalúa si el diseño es moderno, o si parece antiguo, si tiene mala resolución o es poco profesional. "
            "Responde con una única palabra inicial: 'APROBADO' (si se ve moderno y profesional) o 'RECHAZADO' (si necesita un rediseño urgente). "
            "Luego, en la misma línea, escribe un guión '-' y da una breve razón de 1 sola frase del por qué. "
            "Ejemplo: RECHAZADO - El diseño parece de los años 2000, no está optimizado y los colores chocan."
        )
        
        response_eval = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[img, prompt_eval]
        )
        evaluacion = response_eval.text.strip()
        
        # 2. Generación del Correo
        prompt_email = (
            f"Escribe un correo electrónico de ventas frío (cold email) corto y persuasivo dirigido al dueño de '{business_name}'. "
            f"El correo debe mencionar que visitaste su página web ({website_url}) y notaste lo siguiente: {evaluacion}. "
            "Ofrécele tus servicios de creación de páginas web modernas con Inteligencia Artificial. "
            "Dile que puedes hacerle un prototipo gratuito en 48 horas. "
            "Mantén un tono profesional pero cercano, no más de 3 párrafos."
        )
        
        response_email = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt_email
        )
        correo = response_email.text.strip()
        
        return evaluacion, correo
    except Exception as e:
        return f"Error en IA: {str(e)}", "No se pudo generar el correo."

# --- INTERFAZ PRINCIPAL ---

if st.sidebar.button("🚀 Iniciar Prospección Automática", type="primary"):
    if not gmaps_api_key or not gemini_api_key:
        st.warning("⚠️ Por favor, ingresa tus API Keys en el panel lateral antes de continuar.")
    else:
        st.info(f"Buscando '{search_query}'...")
        
        with st.spinner("1️⃣ Extrayendo negocios de Google Maps..."):
            leads = get_places(search_query, gmaps_api_key, max_results)
            
        if not leads:
            st.error("No se encontraron resultados o hubo un error con la API de Google Maps.")
        else:
            st.success(f"¡Se encontraron {len(leads)} prospectos!")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            resultados_finales = []
            
            for i, lead in enumerate(leads):
                status_text.text(f"Analizando prospecto {i+1}/{len(leads)}: {lead['Nombre']}...")
                
                evaluacion = "N/A"
                correo = "N/A"
                
                if lead['Website'] == 'No tiene':
                    evaluacion = "CLIENTE IDEAL - No tiene página web."
                    
                    # Generar correo para quien no tiene web
                    try:
                        client = genai.Client(api_key=gemini_api_key)
                        prompt_no_web = f"Escribe un correo corto de ventas al dueño de '{lead['Nombre']}'. Dile que los buscaste en internet y notaste que no tienen página web, lo cual les hace perder clientes. Ofrécele hacerles una web moderna con IA. Tono profesional."
                        resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_no_web)
                        correo = resp.text.strip()
                    except:
                        correo = "Error al generar."
                else:
                    status_text.text(f"Tomando captura web de {lead['Nombre']}...")
                    img = get_website_screenshot(lead['Website'])
                    
                    if img:
                        status_text.text(f"La IA está evaluando el diseño de {lead['Nombre']}...")
                        evaluacion, correo = evaluate_website_and_write_email(img, lead['Website'], lead['Nombre'], gemini_api_key)
                    else:
                        evaluacion = "Error al cargar la página."
                        correo = "No se pudo generar porque la web falló al cargar."
                
                # Guardar resultado
                lead_data = {
                    "Negocio": lead['Nombre'],
                    "Teléfono": lead['Teléfono'],
                    "Website": lead['Website'],
                    "Diagnóstico IA": evaluacion,
                    "Correo Generado": correo
                }
                resultados_finales.append(lead_data)
                
                progress_bar.progress((i + 1) / len(leads))
                time.sleep(1) # Pequeña pausa para no saturar APIs
                
            status_text.text("¡Prospección completada! 🎉")
            
            # Mostrar resultados en tabla
            df = pd.DataFrame(resultados_finales)
            st.dataframe(df)
            
            # Botón de Descarga Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Leads')
            
            excel_data = output.getvalue()
            
            st.download_button(
                label="📥 Descargar Leads en Excel (.xlsx)",
                data=excel_data,
                file_name="prospectos_generados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
