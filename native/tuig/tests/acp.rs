use serde_json::{Value, json};
use tokio::io::{
    AsyncBufReadExt, AsyncWriteExt, BufReader, DuplexStream, ReadHalf, WriteHalf, split,
};
use tuig_native::acp::{MAX_FRAME_BYTES, TextClient, completed};

type Peer = (BufReader<ReadHalf<DuplexStream>>, WriteHalf<DuplexStream>);

async fn receive(peer: &mut Peer) -> Value {
    let mut line = String::new();
    peer.0.read_line(&mut line).await.unwrap();
    serde_json::from_str(&line).unwrap()
}

async fn send(peer: &mut Peer, value: Value) {
    peer.1
        .write_all(format!("{value}\n").as_bytes())
        .await
        .unwrap();
}

async fn setup(peer: &mut Peer) {
    let initialize = receive(peer).await;
    assert_eq!(initialize["method"], "initialize");
    assert_eq!(initialize["params"]["protocolVersion"], 1);
    assert_eq!(initialize["params"]["clientCapabilities"], json!({}));
    send(peer, json!({"jsonrpc":"2.0","id":1,"result":{"protocolVersion":1,"agentCapabilities":{"sessionCapabilities":{"close":{}}}}})).await;
    let create = receive(peer).await;
    assert_eq!(
        create["params"],
        json!({"cwd":"/workspace","mcpServers":[]})
    );
    send(
        peer,
        json!({"jsonrpc":"2.0","id":2,"result":{"sessionId":"s"}}),
    )
    .await;
}

fn update(session: &str, text: &str) -> Value {
    json!({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":session,"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":text}}}})
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn scripted_v1_text_turn_and_close_preserve_wire_order() {
    let (local, remote) = tokio::io::duplex(4096);
    let (reader, writer) = split(local);
    let (remote_reader, remote_writer) = split(remote);
    let backend = tokio::spawn(async move {
        let mut peer = (BufReader::new(remote_reader), remote_writer);
        setup(&mut peer).await;
        let prompt = receive(&mut peer).await;
        assert_eq!(
            prompt["params"],
            json!({"sessionId":"s","prompt":[{"type":"text","text":"hello"}]})
        );
        send(&mut peer, update("s", "one ")).await;
        send(&mut peer, update("s", "two")).await;
        send(
            &mut peer,
            json!({"jsonrpc":"2.0","id":3,"result":{"stopReason":"end_turn"}}),
        )
        .await;
        assert_eq!(receive(&mut peer).await["method"], "session/close");
        send(&mut peer, json!({"jsonrpc":"2.0","id":4,"result":{}})).await;
    });
    let mut client = TextClient::new(reader, writer);
    client.initialize("/workspace").await.unwrap();
    client.prompt("hello").await.unwrap();
    let mut text = String::new();
    let result = client
        .response(3, async |chunk| {
            text.push_str(chunk);
            Ok(())
        })
        .await
        .unwrap();
    completed(&result).unwrap();
    assert_eq!(text, "one two");
    assert!(client.prompt("replay").await.is_err());
    client.close().await.unwrap();
    backend.await.unwrap();
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn cancellation_is_notification_and_requires_prompt_response() {
    let (local, remote) = tokio::io::duplex(4096);
    let (reader, writer) = split(local);
    let (remote_reader, remote_writer) = split(remote);
    let backend = tokio::spawn(async move {
        let mut peer = (BufReader::new(remote_reader), remote_writer);
        setup(&mut peer).await;
        receive(&mut peer).await;
        assert_eq!(
            receive(&mut peer).await,
            json!({"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"s"}})
        );
        send(&mut peer, update("s", "last chunk")).await;
        send(
            &mut peer,
            json!({"jsonrpc":"2.0","id":3,"result":{"stopReason":"cancelled"}}),
        )
        .await;
    });
    let mut client = TextClient::new(reader, writer);
    client.initialize("/workspace").await.unwrap();
    client.prompt("hello").await.unwrap();
    client.cancel().await.unwrap();
    let result = client.response(3, async |_| Ok(())).await.unwrap();
    assert_eq!(completed(&result), Err("Local ACP turn canceled"));
    backend.await.unwrap();
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn rejects_foreign_ids_sessions_errors_and_unsupported_updates() {
    for bad in [
        json!({"jsonrpc":"2.0","id":4,"result":{"stopReason":"end_turn"}}),
        json!({"jsonrpc":"2.0","id":"3","result":{"stopReason":"end_turn"}}),
        json!({"jsonrpc":"2.0","id":3,"result":{},"error":{"code":-1}}),
        json!({"jsonrpc":"2.0","id":3,"error":{"code":-1,"message":"secret must not render"}}),
        update("foreign", "must not render"),
        json!({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s","update":{"sessionUpdate":"tool_call"}}}),
    ] {
        let (local, remote) = tokio::io::duplex(4096);
        let (reader, writer) = split(local);
        let (rr, rw) = split(remote);
        let backend = tokio::spawn(async move {
            let mut peer = (BufReader::new(rr), rw);
            setup(&mut peer).await;
            receive(&mut peer).await;
            send(&mut peer, bad).await;
        });
        let mut client = TextClient::new(reader, writer);
        client.initialize("/workspace").await.unwrap();
        client.prompt("hello").await.unwrap();
        assert!(
            client
                .response(3, async |_| panic!("rejected output rendered"))
                .await
                .is_err()
        );
        backend.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn client_requests_fail_closed_without_permission_or_host_effects() {
    for method in [
        "fs/read_text_file",
        "terminal/create",
        "session/request_permission",
        "unknown",
    ] {
        let (local, remote) = tokio::io::duplex(4096);
        let (reader, writer) = split(local);
        let (rr, rw) = split(remote);
        let backend = tokio::spawn(async move {
            let mut peer = (BufReader::new(rr), rw);
            setup(&mut peer).await;
            receive(&mut peer).await;
            send(
                &mut peer,
                json!({"jsonrpc":"2.0","id":"callback","method":method,"params":{}}),
            )
            .await;
            let refusal = receive(&mut peer).await;
            assert_eq!(refusal["id"], "callback");
            if method == "session/request_permission" {
                assert_eq!(refusal["result"]["outcome"]["outcome"], "cancelled");
            } else {
                assert_eq!(refusal["error"]["code"], -32601);
            }
        });
        let mut client = TextClient::new(reader, writer);
        client.initialize("/workspace").await.unwrap();
        client.prompt("hello").await.unwrap();
        assert!(client.response(3, async |_| Ok(())).await.is_err());
        backend.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn initialization_rejects_version_mismatch_eof_and_oversized_frames() {
    for bytes in [
        b"{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":2}}\n".to_vec(),
        b"{\"partial\":".to_vec(),
        vec![b'x'; MAX_FRAME_BYTES + 1],
        vec![0xff, b'\n'],
    ] {
        let mut client = TextClient::new(bytes.as_slice(), tokio::io::sink());
        assert!(client.initialize("/workspace").await.is_err());
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn interrupted_read_preserves_partial_frame_during_cancel_drain() {
    let (local, remote) = tokio::io::duplex(4096);
    let (reader, writer) = split(local);
    let (rr, rw) = split(remote);
    let backend = tokio::spawn(async move {
        let mut peer = (BufReader::new(rr), rw);
        setup(&mut peer).await;
        receive(&mut peer).await;
        let frame = format!("{}\n", update("s", "final"));
        peer.1.write_all(&frame.as_bytes()[..10]).await.unwrap();
        assert_eq!(receive(&mut peer).await["method"], "session/cancel");
        peer.1.write_all(&frame.as_bytes()[10..]).await.unwrap();
        send(
            &mut peer,
            json!({"jsonrpc":"2.0","id":3,"result":{"stopReason":"cancelled"}}),
        )
        .await;
    });
    let mut client = TextClient::new(reader, writer);
    client.initialize("/workspace").await.unwrap();
    client.prompt("hello").await.unwrap();
    assert!(
        tokio::time::timeout(
            std::time::Duration::from_millis(20),
            client.response(3, async |_| Ok(()))
        )
        .await
        .is_err()
    );
    client.cancel().await.unwrap();
    let mut text = String::new();
    let result = client
        .response(3, async |chunk| {
            text.push_str(chunk);
            Ok(())
        })
        .await
        .unwrap();
    assert_eq!(text, "final");
    assert_eq!(completed(&result), Err("Local ACP turn canceled"));
    backend.await.unwrap();
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn cumulative_text_limit_stops_before_delivering_excess_output() {
    let mut wire = String::from(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":1}}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"sessionId\":\"s\"}}\n",
    );
    for _ in 0..22 {
        wire.push_str(&format!("{}\n", update("s", &"x".repeat(200_000))));
    }
    let mut client = TextClient::new(wire.as_bytes(), tokio::io::sink());
    client.initialize("/workspace").await.unwrap();
    client.prompt("hello").await.unwrap();
    let mut delivered = 0;
    assert_eq!(
        client
            .response(3, async |chunk| {
                delivered += chunk.len();
                Ok(())
            })
            .await,
        Err("ACP output limit")
    );
    assert_eq!(delivered, 4_000_000);
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn local_prompt_and_encoded_request_respect_backend_limits() {
    for prompt in ["x".repeat(16_385), "\0".repeat(16_384)] {
        let wire = b"{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":1}}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"sessionId\":\"s\"}}\n";
        let mut client = TextClient::new(wire.as_slice(), tokio::io::sink());
        client.initialize("/workspace").await.unwrap();
        assert!(client.prompt(&prompt).await.is_err());
        assert!(client.response(3, async |_| Ok(())).await.is_err());
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn sequential_turns_require_acknowledgement_and_monotonic_ids() {
    let (local, remote) = tokio::io::duplex(4096);
    let (reader, writer) = split(local);
    let (rr, rw) = split(remote);
    let backend = tokio::spawn(async move {
        let mut peer = (BufReader::new(rr), rw);
        setup(&mut peer).await;
        for (id, stop) in [(3, "end_turn"), (4, "cancelled"), (5, "end_turn")] {
            let prompt = receive(&mut peer).await;
            assert_eq!(prompt["id"], id);
            assert_eq!(prompt["params"]["sessionId"], "s");
            if id == 4 {
                assert_eq!(receive(&mut peer).await["method"], "session/cancel");
            }
            send(&mut peer, update("s", "text")).await;
            send(
                &mut peer,
                json!({"jsonrpc":"2.0","id":id,"result":{"stopReason":stop}}),
            )
            .await;
        }
        assert_eq!(receive(&mut peer).await["id"], 6);
        send(&mut peer, json!({"jsonrpc":"2.0","id":6,"result":{}})).await;
    });
    let mut client = TextClient::new(reader, writer).with_sequential_turns();
    client.initialize("/workspace").await.unwrap();
    for expected in 3..=5 {
        let id = client.prompt("turn").await.unwrap();
        assert_eq!(id, expected);
        assert!(client.prompt("duplicate").await.is_err());
        if id == 4 {
            client.cancel().await.unwrap();
        }
        let response = client.response(id, async |_| Ok(())).await.unwrap();
        assert!(matches!(
            response["stopReason"].as_str(),
            Some("end_turn" | "cancelled")
        ));
    }
    client.close().await.unwrap();
    backend.await.unwrap();
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn unknown_or_refused_turn_never_permits_sequential_replay() {
    for response in [
        json!({"jsonrpc":"2.0","id":3,"result":{"stopReason":"max_tokens"}}),
        json!({"jsonrpc":"2.0","id":3,"error":{"code":-1}}),
        json!({"jsonrpc":"2.0","id":4,"result":{"stopReason":"end_turn"}}),
    ] {
        let (local, remote) = tokio::io::duplex(4096);
        let (reader, writer) = split(local);
        let (rr, rw) = split(remote);
        let backend = tokio::spawn(async move {
            let mut peer = (BufReader::new(rr), rw);
            setup(&mut peer).await;
            receive(&mut peer).await;
            send(&mut peer, response).await;
        });
        let mut client = TextClient::new(reader, writer).with_sequential_turns();
        client.initialize("/workspace").await.unwrap();
        let id = client.prompt("turn").await.unwrap();
        let _ = client.response(id, async |_| Ok(())).await;
        assert!(client.prompt("must not send").await.is_err());
        backend.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn sequential_output_budget_resets_only_for_an_acknowledged_next_turn() {
    let mut wire = String::from(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":1}}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"sessionId\":\"s\"}}\n",
    );
    for id in [3, 4] {
        for _ in 0..20 {
            wire.push_str(&format!("{}\n", update("s", &"x".repeat(150_000))));
        }
        wire.push_str(&format!(
            "{}\n",
            json!({"jsonrpc":"2.0","id":id,"result":{"stopReason":"end_turn"}})
        ));
    }
    let mut client = TextClient::new(wire.as_bytes(), tokio::io::sink()).with_sequential_turns();
    client.initialize("/workspace").await.unwrap();
    for _ in 0..2 {
        let id = client.prompt("turn").await.unwrap();
        let mut delivered = 0;
        client
            .response(id, async |text| {
                delivered += text.len();
                Ok(())
            })
            .await
            .unwrap();
        assert_eq!(delivered, 3_000_000);
    }
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn unsolicited_idle_frames_cannot_become_the_next_turn() {
    let mut wire = String::from(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":1}}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"sessionId\":\"s\"}}\n",
    );
    wire.push_str(&format!("{}\n", update("s", "unsolicited")));
    let mut client = TextClient::new(wire.as_bytes(), tokio::io::sink()).with_sequential_turns();
    client.initialize("/workspace").await.unwrap();
    assert_eq!(
        client.idle().await,
        Err("Unsolicited ACP message between turns")
    );
    assert!(client.prompt("must not send").await.is_err());
}

// spec: TUIG-RUNTIME-R011.14
#[tokio::test]
async fn partial_idle_frame_is_not_attached_to_a_new_prompt() {
    let (local, mut remote) = tokio::io::duplex(4096);
    remote.write_all(b"{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":1}}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"sessionId\":\"s\"}}\n{\"jsonrpc\":").await.unwrap();
    let (read, write) = split(local);
    let mut client = TextClient::new(read, write).with_sequential_turns();
    client.initialize("/workspace").await.unwrap();
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(10), client.idle())
            .await
            .is_err()
    );
    assert_eq!(
        client.prompt("must not send").await,
        Err("Partial unsolicited ACP frame; session cannot continue")
    );
}
