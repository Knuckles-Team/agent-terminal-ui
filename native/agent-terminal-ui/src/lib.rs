use reqwest::{Client, Url, header};
use std::time::Duration;

const MAX_CARD_BYTES: usize = 1024 * 1024;

pub struct GraphOsClient {
    http: Client,
    card_url: Url,
}

impl GraphOsClient {
    pub fn new(endpoint: &str, token: Option<&str>) -> Result<Self, &'static str> {
        if endpoint
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
        {
            return Err("Invalid GraphOS endpoint");
        }
        let mut url = Url::parse(endpoint).map_err(|_| "Invalid GraphOS endpoint")?;
        if !matches!(url.scheme(), "http" | "https")
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || url.path() != "/"
            || url.port() == Some(0)
        {
            return Err("Invalid GraphOS endpoint");
        }
        let local = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
        if !local && url.scheme() != "https" {
            return Err("Remote GraphOS requires TLS");
        }
        if !local && token.is_none() {
            return Err("Remote GraphOS requires a caller credential");
        }
        let mut headers = header::HeaderMap::new();
        if let Some(token) = token {
            if token.is_empty() || !token.bytes().all(|c| (33..=126).contains(&c)) {
                return Err("Invalid caller credential");
            }
            let mut value = header::HeaderValue::from_str(&format!("Bearer {token}"))
                .map_err(|_| "Invalid caller credential")?;
            value.set_sensitive(true);
            headers.insert(header::AUTHORIZATION, value);
        }
        url.set_path("/.well-known/agent-card.json");
        let http = Client::builder()
            .default_headers(headers)
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|_| "Cannot initialize GraphOS transport")?;
        Ok(Self {
            http,
            card_url: url,
        })
    }

    pub async fn discover(&self) -> Result<String, &'static str> {
        let mut response = self
            .http
            .get(self.card_url.clone())
            .send()
            .await
            .map_err(|_| "GraphOS discovery failed or timed out")?;
        if !response.status().is_success() {
            return Err("GraphOS discovery refused or unavailable");
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "GraphOS response interrupted")?
        {
            if chunk.len() > MAX_CARD_BYTES.saturating_sub(bytes.len()) {
                return Err("GraphOS Agent Card exceeds size limit");
            }
            bytes.extend_from_slice(&chunk);
        }
        let card: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|_| "Invalid GraphOS Agent Card")?;
        let name = card
            .get("name")
            .and_then(|v| v.as_str())
            .filter(|name| !name.trim().is_empty())
            .ok_or("GraphOS Agent Card has no name")?;
        Ok(name.chars().filter(|c| !c.is_control()).take(80).collect())
    }
}
