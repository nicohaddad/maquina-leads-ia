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

st.sidebar.markdown("---")
st.sidebar.header("🧠 Personalización de IA (Prompts)")
with st.sidebar.expander("Modificar Instrucciones de IA", expanded=False):
    st.caption("Puedes usar las variables {business_name}, {website_url} y {evaluacion} en tus correos.")
    prompt_eval_input = st.text_area(
        "Prompt de Evaluación Visual",
        value="Eres un experto diseñador web. Revisa la captura de pantalla de esta página web. Evalúa si el diseño es moderno, o si parece antiguo, si tiene mala resolución o es poco profesional. Responde con una única palabra inicial: 'APROBADO' o 'RECHAZADO'. Luego, en la misma línea, escribe un guión '-' y da una breve razón de 1 sola frase del por qué. Ejemplo: RECHAZADO - El diseño parece de los años 2000 y los colores chocan.",
        height=150
    )
    prompt_email_input = st.text_area(
        "Prompt de Correo (Tienen Web)",
        value="Escribe un correo de ventas frío corto dirigido al dueño de '{business_name}'. Dile que visitaste su página web ({website_url}) y notaste lo siguiente: {evaluacion}. Ofrécele tus servicios de creación de páginas web con IA. Ofrece un prototipo gratis en 48h. Tono profesional, máximo 3 párrafos.",
        height=150
    )
    prompt_noweb_input = st.text_area(
        "Prompt de Correo (NO Tienen Web)",
        value="Escribe un correo corto de ventas al dueño de '{business_name}'. Dile que los buscaste en internet y notaste que no tienen página web, lo cual les hace perder clientes. Ofrécele hacerles una web moderna con IA. Tono profesional.",
        height=100
    )

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

def evaluate_website_and_write_email(img, website_url, business_name, gemini_key, custom_prompt_eval, custom_prompt_email):
    """Usa Gemini para evaluar la imagen y redactar el correo."""
    try:
        client = genai.Client(api_key=gemini_key)
        tokens_in = 0
        tokens_out = 0
        
        # 1. Evaluación Visual
        response_eval = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[img, custom_prompt_eval]
        )
        evaluacion = response_eval.text.strip()
        if hasattr(response_eval, 'usage_metadata') and response_eval.usage_metadata:
            tokens_in += getattr(response_eval.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_eval.usage_metadata, 'candidates_token_count', 0)
        
        # 2. Generación del Correo
        # Reemplazo seguro de variables
        prompt_email = custom_prompt_email.replace("{business_name}", business_name).replace("{website_url}", website_url).replace("{evaluacion}", evaluacion)

        
        response_email = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt_email
        )
        correo = response_email.text.strip()
        if hasattr(response_email, 'usage_metadata') and response_email.usage_metadata:
            tokens_in += getattr(response_email.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_email.usage_metadata, 'candidates_token_count', 0)
        
        return evaluacion, correo, tokens_in, tokens_out
    except Exception as e:
        return f"Error en IA: {str(e)}", "No se pudo generar el correo.", 0, 0

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
            
            # --- Métricas de Costo ---
            col1, col2, col3 = st.columns(3)
            metric_leads = col1.empty()
            metric_tokens = col2.empty()
            metric_cost = col3.empty()
            
            total_tokens_in = 0
            total_tokens_out = 0
            
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
                        prompt_no_web = prompt_noweb_input.replace("{business_name}", lead['Nombre'])
                        resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_no_web)
                        correo = resp.text.strip()
                        if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                            total_tokens_in += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                            total_tokens_out += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                    except:
                        correo = "Error al generar."
                else:
                    status_text.text(f"Tomando captura web de {lead['Nombre']}...")
                    img = get_website_screenshot(lead['Website'])
                    
                    if img:
                        status_text.text(f"La IA está evaluando el diseño de {lead['Nombre']}...")
                        evaluacion, correo, t_in, t_out = evaluate_website_and_write_email(img, lead['Website'], lead['Nombre'], gemini_api_key, prompt_eval_input, prompt_email_input)
                        total_tokens_in += t_in
                        total_tokens_out += t_out
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
                
                # Actualizar Métricas en tiempo real
                metric_leads.metric("Prospectos Analizados", f"{i+1}/{len(leads)}")
                metric_tokens.metric("Tokens Usados", f"{total_tokens_in + total_tokens_out:,}")
                
                # Costo estimado Gemini 1.5 Pro ($1.25 / 1M prompt, $3.75 / 1M completion)
                costo_estimado = (total_tokens_in / 1_000_000 * 1.25) + (total_tokens_out / 1_000_000 * 3.75)
                metric_cost.metric("Costo Estimado (USD)", f"${costo_estimado:.4f}")
                
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
