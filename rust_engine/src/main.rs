use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{self, Read};

#[derive(Debug, Clone, Deserialize)]
struct EdgeInput {
    token_in: String,
    token_out: String,
    rate: String,
    pool_id: String,
    protocol: String,
}

#[derive(Debug, Deserialize)]
struct Request {
    edges: Vec<EdgeInput>,
}

#[derive(Debug, Clone)]
struct Edge {
    u: usize,
    v: usize,
    weight: f64,
    rate: f64,
    pool_id: String,
    protocol: String,
}

#[derive(Debug, Clone, Serialize)]
struct EdgeOutput {
    token_in: String,
    token_out: String,
    pool_id: String,
    protocol: String,
    rate: f64,
}

#[derive(Debug, Clone, Serialize)]
struct Opportunity {
    path: Vec<String>,
    edges: Vec<EdgeOutput>,
    cumulative_rate: f64,
    profit_pct: f64,
    detector: String,
}

#[derive(Debug, Serialize)]
struct Response {
    engine: String,
    opportunities: Vec<Opportunity>,
}

fn canonical_cycle_key(path: &[usize]) -> Vec<usize> {
    let mut best: Option<Vec<usize>> = None;
    for idx in 0..path.len() {
        let mut rotated = Vec::with_capacity(path.len());
        rotated.extend_from_slice(&path[idx..]);
        rotated.extend_from_slice(&path[..idx]);
        if best.as_ref().map_or(true, |current| rotated < *current) {
            best = Some(rotated);
        }
    }
    best.unwrap_or_default()
}

fn detect_negative_cycles(tokens: &[String], edges: &[Edge]) -> Vec<Opportunity> {
    let n = tokens.len();
    let mut seen: BTreeSet<Vec<usize>> = BTreeSet::new();
    let mut out: Vec<Opportunity> = Vec::new();
    if n == 0 || edges.is_empty() {
        return out;
    }

    for source in 0..n {
        let mut dist = vec![f64::INFINITY; n];
        let mut pred: Vec<Option<usize>> = vec![None; n];
        let mut pred_edge: Vec<Option<usize>> = vec![None; n];
        dist[source] = 0.0;

        for _ in 0..n.saturating_sub(1) {
            let mut updated = false;
            for (edge_idx, edge) in edges.iter().enumerate() {
                if dist[edge.u].is_finite() && dist[edge.u] + edge.weight < dist[edge.v] {
                    dist[edge.v] = dist[edge.u] + edge.weight;
                    pred[edge.v] = Some(edge.u);
                    pred_edge[edge.v] = Some(edge_idx);
                    updated = true;
                }
            }
            if !updated {
                break;
            }
        }

        for edge in edges {
            if !(dist[edge.u].is_finite() && dist[edge.u] + edge.weight < dist[edge.v]) {
                continue;
            }

            let mut cycle_node = edge.v;
            let mut valid = true;
            for _ in 0..n {
                match pred[cycle_node] {
                    Some(prev) => cycle_node = prev,
                    None => {
                        valid = false;
                        break;
                    }
                }
            }
            if !valid {
                continue;
            }

            let mut path_rev: Vec<usize> = Vec::new();
            let mut edge_rev: Vec<usize> = Vec::new();
            let mut first_seen: BTreeMap<usize, usize> = BTreeMap::new();
            let mut cur = cycle_node;
            loop {
                if let Some(idx) = first_seen.get(&cur).copied() {
                    path_rev = path_rev[idx..].to_vec();
                    edge_rev = edge_rev[idx..].to_vec();
                    break;
                }
                first_seen.insert(cur, path_rev.len());
                path_rev.push(cur);
                let Some(edge_idx) = pred_edge[cur] else { break };
                edge_rev.push(edge_idx);
                let Some(prev) = pred[cur] else { break };
                cur = prev;
            }

            if path_rev.len() < 2 || edge_rev.len() < 2 || path_rev.len() != edge_rev.len() {
                continue;
            }

            path_rev.reverse();
            let mut ordered_edge_indices: Vec<usize> = Vec::with_capacity(path_rev.len());
            for idx in 0..path_rev.len() {
                let next_node = if idx + 1 < path_rev.len() {
                    path_rev[idx + 1]
                } else {
                    path_rev[0]
                };
                let Some(edge_idx) = pred_edge[next_node] else {
                    valid = false;
                    break;
                };
                ordered_edge_indices.push(edge_idx);
            }
            if !valid {
                continue;
            }

            let key = canonical_cycle_key(&path_rev);
            if key.is_empty() || !seen.insert(key) {
                continue;
            }

            let mut cumulative_rate = 1.0_f64;
            let mut edge_outputs = Vec::with_capacity(ordered_edge_indices.len());
            for edge_idx in &ordered_edge_indices {
                let e = &edges[*edge_idx];
                cumulative_rate *= e.rate;
                edge_outputs.push(EdgeOutput {
                    token_in: tokens[e.u].clone(),
                    token_out: tokens[e.v].clone(),
                    pool_id: e.pool_id.clone(),
                    protocol: e.protocol.clone(),
                    rate: e.rate,
                });
            }
            if cumulative_rate <= 1.0 {
                continue;
            }

            let mut path: Vec<String> = path_rev.iter().map(|idx| tokens[*idx].clone()).collect();
            if let Some(first) = path.first().cloned() {
                path.push(first);
            }
            out.push(Opportunity {
                path,
                edges: edge_outputs,
                cumulative_rate,
                profit_pct: (cumulative_rate - 1.0) * 100.0,
                detector: "RUST_BELLMAN_FORD".to_string(),
            });
        }
    }
    out.sort_by(|a, b| b.profit_pct.partial_cmp(&a.profit_pct).unwrap_or(std::cmp::Ordering::Equal));
    out
}

fn run() -> Result<Response, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|err| format!("stdin_read_failed: {err}"))?;
    let request: Request = serde_json::from_str(&input).map_err(|err| format!("json_decode_failed: {err}"))?;

    let mut token_set: BTreeSet<String> = BTreeSet::new();
    for edge in &request.edges {
        let Ok(rate) = edge.rate.parse::<f64>() else {
            continue;
        };
        if rate > 0.0 && rate.is_finite() {
            token_set.insert(edge.token_in.clone());
            token_set.insert(edge.token_out.clone());
        }
    }
    let tokens: Vec<String> = token_set.into_iter().collect();
    let token_index: BTreeMap<String, usize> = tokens
        .iter()
        .enumerate()
        .map(|(idx, token)| (token.clone(), idx))
        .collect();

    let edges: Vec<Edge> = request
        .edges
        .into_iter()
        .filter_map(|edge| {
            let rate: f64 = edge.rate.parse().ok()?;
            if !(rate > 0.0 && rate.is_finite()) {
                return None;
            }
            let u = *token_index.get(&edge.token_in)?;
            let v = *token_index.get(&edge.token_out)?;
            Some(Edge {
                u,
                v,
                weight: -rate.ln(),
                rate,
                pool_id: edge.pool_id,
                protocol: edge.protocol,
            })
        })
        .collect();

    Ok(Response {
        engine: "omega_rust_engine".to_string(),
        opportunities: detect_negative_cycles(&tokens, &edges),
    })
}

fn main() {
    match run() {
        Ok(response) => {
            println!("{}", serde_json::to_string(&response).expect("response_json_encode"));
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
