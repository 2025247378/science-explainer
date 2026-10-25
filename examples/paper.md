# DeepGill: A Lightweight Vision Model for Fish Disease Recognition in Recirculating Aquaculture Systems

Liang Chen, Yue Wang, Ming Zhao
School of Fisheries, Ocean University, China

> 本文件为 science-explainer 的示例输入，内容为**虚构论文**，仅用于演示脚本与两种模式的输出，不指向任何真实研究。

## Abstract

Fish disease inspection in recirculating aquaculture systems relies on manual patrol, which is slow and error-prone. We propose DeepGill, a two-stage lightweight vision model that first locates individual fish and then classifies their health status, distilled from a large teacher model. On 12,400 annotated images from two farms, DeepGill achieves 94.2% five-class accuracy, 6.5 percentage points above the deployed baseline (87.7%), at 21 FPS on an edge device.

## 1. Introduction

Early detection of fish disease is critical in recirculating aquaculture systems. Manual patrol at night is labour intensive and depends on operator experience, which is not reproducible across farms. Prior work applies generic object detectors directly to pond imagery, but these models are trained for terrestrial scenes and degrade under underwater lighting, bubbles and wall reflections.

## 2. Related Work

Generic detectors reach high accuracy on benchmark datasets such as COCO, yet transfer poorly to aquaculture imagery. Two-stage pipelines that decouple localization from classification are common in medical imaging, where lesion-level decisions benefit from per-instance crops.

### 2.3 Deployed baseline

The currently deployed generic detector reaches 87.7% accuracy in field tests on the same two farms.

## 3. Methods

### 3.1 Fish localization

A detection network crops each fish from the frame. Track identity is maintained across consecutive frames so that per-fish decisions are temporally consistent.

### 3.2 Health classification

Each individual fish image is classified into healthy or one of five lesion categories: early red spot, advanced ulcer, fin rot, scale loss and mucus excess.

### 3.4 Alert decision

An alarm fires only after 5 consecutive anomalous frames for the same tracked fish, which suppresses false positives caused by transient occlusion.

## 4. Materials and Methods

### 4.1 Dataset

Data were collected from two commercial recirculating farms over nine months, yielding 12,400 annotated images. Approximately 37% of samples contain visible occlusion or motion blur. Annotation was performed by two veterinarians; inter-annotator agreement is not reported.

### 4.2 Model configuration

The teacher model uses a ViT-B backbone; the student model uses a MobileNetV3 backbone with one-third of the teacher's parameters.

## 5. Results

### 5.2 Distillation

The student model keeps 96% of the teacher's accuracy while using one-third of its parameters.

### 5.3 Accuracy

Five-class overall accuracy is 94.2%, against 87.7% for the deployed baseline, a gain of 6.5 percentage points (Table 3). On the hardest category, early red spot with a mean lesion diameter below 5 mm, the baseline reaches 71% recall and DeepGill reaches 85% (Table 4).

### 5.4 Edge speed

Inference runs at 21 FPS on a commodity edge box with an integrated GPU. All throughput measurements were taken on that single device; no discrete-GPU or multi-stream configuration was evaluated.

## 6. Discussion

### 6.1 Limitations

Parasitic lesions are not covered by the label set. Turbid-water samples are under-represented (fewer than 400 images). The alert threshold requires per-farm tuning and was not evaluated on a third farm. Cross-species generalization was not tested, as both farms raise the same species.

## 7. Conclusion

DeepGill shows that two-stage decomposition plus distillation enables real-time edge fish disease recognition within the conditions studied.

## References

[1] Example reference entry, omitted in this fixture.
