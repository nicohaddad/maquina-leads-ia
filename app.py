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

# Inicializar estado para guardar resultados y no perderlos
if 'resultados' not in st.session_state:
    st.session_state.resultados = None
if 'total_tokens' not in st.session_state:
    st.session_state.total_tokens = 0
if 'costo_estimado' not in st.session_state:
    st.session_state.costo_estimado = 0.0

# --- BARRA LATERAL: CONFIGURACIÓN ---
st.sidebar.header("🔑 Configuración de APIs")
st.sidebar.markdown("Ingresa tus claves para que el sistema funcione.")

# Cargar desde los "Secrets" de la nube si existen
default_gmaps = st.secrets["GMAPS_API_KEY"] if "GMAPS_API_KEY" in st.secrets else ""
default_gemini = st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else ""

gmaps_api_key = st.sidebar.text_input("Google Maps API Key", value=default_gmaps, type="password")
gemini_api_key = st.sidebar.text_input("Gemini API Key", value=default_gemini, type="password")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Parámetros de Búsqueda")
search_query = st.sidebar.text_input("¿Qué buscas?", value="Estéticas en Polanco, CDMX")
max_results = st.sidebar.slider("Límite de negocios a analizar", min_value=1, max_value=20, value=5)
solo_sin_web = st.sidebar.checkbox("🚨 Mostrar SOLO negocios SIN página web", value=False, help="Si marcas esto, el robot ignorará cualquier negocio que ya tenga sitio web.")

st.sidebar.markdown("---")
st.sidebar.header("⭐ Filtros de Calidad (Scoring)")
st.sidebar.caption("Filtra los negocios por su calificación en Google Maps.")
min_rating = st.sidebar.slider("Rating Mínimo", 0.0, 5.0, 0.0, 0.5)
max_rating = st.sidebar.slider("Rating Máximo", 0.0, 5.0, 5.0, 0.5)

with st.sidebar.expander("Ajuste Fino de Puntos (Matriz)", expanded=False):
    st.caption("Puntos otorgados a cada criterio para calcular el Score Final.")
    pts_resenas_altas = st.number_input("100+ Reseñas", value=10)
    pts_resenas_medias = st.number_input("30-99 Reseñas", value=6)
    pts_rating_alto = st.number_input("Rating 4.6+", value=8)
    pts_no_web = st.number_input("No tiene página web", value=15)
    pts_web_mala = st.number_input("Web mala/vieja", value=10)
    pts_premium = st.number_input("Servicios premium", value=10)
    pts_marketing = st.number_input("Instagram activo", value=4)
    pts_whatsapp = st.number_input("WhatsApp visible", value=7)
    pts_agenda = st.number_input("Botón de Agenda/Citas", value=6)

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
    prompt_caido_input = st.text_area(
        "Prompt de Correo (Dominio Caído/Expirado)",
        value="Escribe un correo URGENTE al dueño de '{business_name}'. Dile que intentaste entrar a su página web ({website_url}) desde Google Maps pero está CAÍDA o el dominio expiró. Explícale que están perdiendo clientes todos los días por esto y ofrécele hacerles una web nueva y moderna con IA esta misma semana.",
        height=120
    )

# --- FUNCIONES CORE ---

def get_places(query, api_key, max_results=5, min_rating=0.0, max_rating=5.0, solo_sin_web=False):
    """Obtiene los lugares usando Google Maps API."""
    gmaps = googlemaps.Client(key=api_key)
    try:
        places_result = gmaps.places(query=query)
        results = []
        for place in places_result.get('results', []):
            if len(results) >= max_results:
                break
                
            place_id = place['place_id']
            # Obtener detalles completos
            details = gmaps.place(place_id, fields=['name', 'website', 'formatted_phone_number', 'rating', 'url', 'user_ratings_total'])['result']
            
            rating = details.get('rating', 0.0)
            if not (min_rating <= rating <= max_rating):
                continue
                
            website = details.get('website', 'No tiene')
            if solo_sin_web and website != 'No tiene':
                continue
                
            results.append({
                "Nombre": details.get('name', 'N/A'),
                "Teléfono": details.get('formatted_phone_number', 'N/A'),
                "Website": website,
                "Rating": rating,
                "Reseñas": details.get('user_ratings_total', 0),
                "Google Maps": details.get('url', f"https://www.google.com/maps/place/?q=place_id:{place_id}")
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
    """Usa Gemini para evaluar la imagen y extraer datos clave para el scoring."""
    import json
    try:
        client = genai.Client(api_key=gemini_key)
        tokens_in = 0
        tokens_out = 0
        
        # 1. Evaluación Visual Estructurada
        # Forzamos a la IA a devolver un JSON con la evaluación y los checks de la matriz
        json_prompt = custom_prompt_eval + """
        \n\nIMPORTANTE: Debes responder ÚNICAMENTE con un objeto JSON válido con esta estructura exacta, sin texto extra (no uses markdown de código):
        {
            "aprobado": false,
            "razon": "breve razón aquí",
            "servicios_premium": true o false (si ves botox, láser, faciales premium, etc),
            "instagram_visible": true o false (si ves el logo o link de Instagram),
            "whatsapp_visible": true o false (si ves logo de WhatsApp o número visible),
            "agenda_visible": true o false (si ves botón de 'Agendar', 'Reservar cita')
        }
        """
        response_eval = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[img, json_prompt]
        )
        
        # Limpiar y parsear JSON
        raw_text = response_eval.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        
        try:
            datos_ia = json.loads(raw_text)
        except:
            datos_ia = {"aprobado": False, "razon": "Error al analizar imagen", "servicios_premium": False, "instagram_visible": False, "whatsapp_visible": False, "agenda_visible": False}

        evaluacion_texto = "APROBADO" if datos_ia.get("aprobado") else "RECHAZADO"
        evaluacion_completa = f"{evaluacion_texto} - {datos_ia.get('razon', '')}"

        if hasattr(response_eval, 'usage_metadata') and response_eval.usage_metadata:
            tokens_in += getattr(response_eval.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_eval.usage_metadata, 'candidates_token_count', 0)
            
        # AHORRO DE TOKENS: Si la web es buena, no necesitamos escribirle un correo para venderle otra.
        if datos_ia.get("aprobado"):
            return evaluacion_completa, "DESCARTADO - El cliente ya tiene una web de alta calidad.", tokens_in, tokens_out, datos_ia
        
        # 2. Generación del Correo (Solo si la web fue RECHAZADA)
        prompt_email = custom_prompt_email.replace("{business_name}", business_name).replace("{website_url}", website_url).replace("{evaluacion}", evaluacion_completa)

        
        response_email = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt_email
        )
        correo = response_email.text.strip()
        if hasattr(response_email, 'usage_metadata') and response_email.usage_metadata:
            tokens_in += getattr(response_email.usage_metadata, 'prompt_token_count', 0)
            tokens_out += getattr(response_email.usage_metadata, 'candidates_token_count', 0)
        
        return evaluacion_completa, correo, tokens_in, tokens_out, datos_ia
    except Exception as e:
        return f"Error en IA: {str(e)}", "No se pudo generar el correo.", 0, 0, {}

# --- INTERFAZ PRINCIPAL ---

if st.sidebar.button("🚀 Iniciar Prospección Automática", type="primary"):
    if not gmaps_api_key or not gemini_api_key:
        st.warning("⚠️ Por favor, ingresa tus API Keys en el panel lateral antes de continuar.")
    else:
        st.info(f"Buscando '{search_query}'...")
        
        with st.spinner("1️⃣ Extrayendo negocios de Google Maps..."):
            leads = get_places(search_query, gmaps_api_key, max_results, min_rating, max_rating, solo_sin_web)
            
        if not leads:
            st.error("No se encontraron resultados o hubo un error con la API de Google Maps.")
        else:
            st.success(f"¡Se encontraron {len(leads)} prospectos!")
            
            # --- Métricas en tiempo real ---
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Limpiar contadores de sesión para nueva corrida
            st.session_state.total_tokens = 0
            st.session_state.costo_estimado = 0.0
            
            # Espacios vacíos para actualizar en vivo
            col1, col2 = st.columns(2)
            metric_tokens_live = col1.empty()
            metric_cost_live = col2.empty()
            
            resultados_finales = []
            
            for i, lead in enumerate(leads):
                status_text.text(f"Analizando prospecto {i+1}/{len(leads)}: {lead['Nombre']}...")
                
                evaluacion = "N/A"
                correo = "N/A"
                score = 0
                
                # --- LOGICA DE LEAD SCORING ---
                # 1. Confianza/Reseñas
                resenas = lead['Reseñas']
                if resenas >= 100: score += pts_resenas_altas
                elif resenas >= 30: score += pts_resenas_medias
                
                # 2. Confianza/Rating
                if lead['Rating'] >= 4.6: score += pts_rating_alto
                
                if lead['Website'] == 'No tiene':
                    evaluacion = "CLIENTE IDEAL - No tiene página web."
                    score += pts_no_web # No tiene web
                    
                    # Generar correo para quien no tiene web
                    try:
                        client = genai.Client(api_key=gemini_api_key)
                        prompt_no_web = prompt_noweb_input.replace("{business_name}", lead['Nombre'])
                        resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_no_web)
                        correo = resp.text.strip()
                        if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                            st.session_state.total_tokens += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                            st.session_state.total_tokens += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                    except:
                        correo = "Error al generar."
                else:
                    status_text.text(f"Tomando captura web de {lead['Nombre']}...")
                    img = get_website_screenshot(lead['Website'])
                    
                    if img:
                        status_text.text(f"La IA está evaluando el diseño de {lead['Nombre']}...")
                        evaluacion, correo, t_in, t_out, datos_ia = evaluate_website_and_write_email(img, lead['Website'], lead['Nombre'], gemini_api_key, prompt_eval_input, prompt_email_input)
                        st.session_state.total_tokens += (t_in + t_out)
                        
                        # --- SCORING VISUAL (IA) ---
                        if datos_ia.get('aprobado') == False: score += pts_web_mala
                        if datos_ia.get('servicios_premium'): score += pts_premium
                        if datos_ia.get('instagram_visible'): score += pts_marketing
                        if datos_ia.get('whatsapp_visible'): score += pts_whatsapp
                        if datos_ia.get('agenda_visible'): score += pts_agenda
                        
                    else:
                        evaluacion = "ALERTA ROJA - Sitio web caído o dominio expirado."
                        score += 20  # Es la mejor oportunidad de venta
                        
                        # Generar correo de emergencia para dominio caído
                        try:
                            client = genai.Client(api_key=gemini_api_key)
                            prompt_caido = prompt_caido_input.replace("{business_name}", lead['Nombre']).replace("{website_url}", lead['Website'])
                            resp = client.models.generate_content(model='gemini-2.5-pro', contents=prompt_caido)
                            correo = resp.text.strip()
                            if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                                st.session_state.total_tokens += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                                st.session_state.total_tokens += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                        except:
                            correo = "Error al generar correo de dominio caído."
                
                # Guardar resultado
                lead_data = {
                    "Score": score,
                    "Negocio": lead['Nombre'],
                    "Rating": lead['Rating'],
                    "Reseñas": lead['Reseñas'],
                    "Website": lead['Website'],
                    "Teléfono": lead['Teléfono'],
                    "Link Maps": lead['Google Maps'],
                    "Diagnóstico IA": evaluacion,
                    "Correo Generado": correo
                }
                resultados_finales.append(lead_data)
                
                # Actualizar Métricas en tiempo real
                status_text.text(f"Analizando prospecto {i+1}/{len(leads)}: {lead['Nombre']}...")
                metric_tokens_live.metric("Tokens Usados (En vivo)", f"{st.session_state.total_tokens:,}")
                
                # Costo estimado Gemini 1.5 Pro ($1.25 / 1M prompt, $3.75 / 1M completion)
                # Para simplificar el vivo, usamos un promedio de $2.50 por 1M tokens totales
                st.session_state.costo_estimado = (st.session_state.total_tokens / 1_000_000) * 2.50
                metric_cost_live.metric("Costo Estimado (USD)", f"${st.session_state.costo_estimado:.4f}")
                
                progress_bar.progress((i + 1) / len(leads))
                time.sleep(1) # Pequeña pausa para no saturar APIs
                
            status_text.text("¡Prospección completada! 🎉")
            
            # Guardar en la memoria de la sesión
            st.session_state.resultados = pd.DataFrame(resultados_finales)

# --- MOSTRAR RESULTADOS GUARDADOS ---
if st.session_state.resultados is not None:
    st.markdown("---")
    st.markdown("### 📊 Resultados de tu Prospección")
    
    # Mostrar métricas guardadas de forma permanente
    col1, col2 = st.columns(2)
    col1.metric("Total Tokens Usados", f"{st.session_state.total_tokens:,}")
    col2.metric("Costo Final (USD)", f"${st.session_state.costo_estimado:.4f}")
    
    st.dataframe(st.session_state.resultados)
    
    # Botón de Descarga Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.resultados.to_excel(writer, index=False, sheet_name='Leads')
    
    excel_data = output.getvalue()
    
    st.download_button(
        label="📥 Descargar Leads en Excel (.xlsx)",
        data=excel_data,
        file_name="prospectos_generados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
