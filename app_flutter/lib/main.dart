import 'package:flutter/material.dart';
import 'package:ar_flutter_plugin/ar_flutter_plugin.dart';
import 'package:ar_flutter_plugin/datatypes/config_planedetection.dart';
import 'package:ar_flutter_plugin/datatypes/node_types.dart';
import 'package:ar_flutter_plugin/datatypes/hittest_result_types.dart';
import 'package:ar_flutter_plugin/managers/ar_session_manager.dart';
import 'package:ar_flutter_plugin/managers/ar_object_manager.dart';
import 'package:ar_flutter_plugin/managers/ar_anchor_manager.dart';
import 'package:ar_flutter_plugin/managers/ar_location_manager.dart';
import 'package:ar_flutter_plugin/models/ar_node.dart';
import 'package:ar_flutter_plugin/models/ar_hittest_result.dart';
import 'package:vector_math/vector_math_64.dart' as vector;

void main() {
  runApp(const FurniVisionApp());
}

class FurniVisionApp extends StatelessWidget {
  const FurniVisionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FurniVision AR Test',
      home: const ARTestScreen(),
    );
  }
}

class ARTestScreen extends StatefulWidget {
  const ARTestScreen({super.key});

  @override
  State<ARTestScreen> createState() => _ARTestScreenState();
}

class _ARTestScreenState extends State<ARTestScreen> {
  late ARSessionManager arSessionManager;
  late ARObjectManager arObjectManager;
  late ARAnchorManager arAnchorManager;

  // One real model from your catalog, for this first proof.
  static const String testModelUrl =
      "http://172.19.94.193:8000/models_3d/scandinavian_platform_bed.glb";

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('FurniVision — AR test')),
      body: ARView(
        onARViewCreated: onARViewCreated,
        planeDetectionConfig: PlaneDetectionConfig.horizontal,
      ),
    );
  }

  void onARViewCreated(
    ARSessionManager sessionManager,
    ARObjectManager objectManager,
    ARAnchorManager anchorManager,
    ARLocationManager locationManager,
  ) {
    arSessionManager = sessionManager;
    arObjectManager = objectManager;
    arAnchorManager = anchorManager;

    arSessionManager.onInitialize(
      showFeaturePoints: false,
      showPlanes: true,
      showWorldOrigin: false,
    );
    arObjectManager.onInitialize();

    arSessionManager.onPlaneOrPointTap = onPlaneTapped;
  }

  Future<void> onPlaneTapped(List<ARHitTestResult> hitTestResults) async {
    final hit = hitTestResults.firstWhere(
      (r) => r.type == ARHitTestResultType.plane,
      orElse: () => hitTestResults.first,
    );

    final newNode = ARNode(
      type: NodeType.webGLB,
      uri: testModelUrl,
      scale: vector.Vector3(1.0, 1.0, 1.0),
      position: hit.worldTransform.getTranslation(),
      rotation: vector.Vector4(1.0, 0.0, 0.0, 0.0),
    );

    final didAdd = await arObjectManager.addNode(newNode);
    if (!didAdd!) {
      debugPrint("Failed to add node to AR scene.");
    }
  }

  @override
  void dispose() {
    arSessionManager.dispose();
    super.dispose();
  }
}